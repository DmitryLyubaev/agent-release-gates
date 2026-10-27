import hashlib
import json
import os
import tempfile
from pathlib import Path

from agent_release_gates.contracts.artifacts import ArtifactBundle, ArtifactReceipt, TraceEvent


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_bundle(raw: dict) -> ArtifactBundle:
    bundle = ArtifactBundle.model_validate(raw)
    if set(bundle.documents) != set(bundle.manifest.documents):
        raise ValueError('DOCUMENT_SET_MISMATCH')
    for name, document in bundle.documents.items():
        if digest(document) != bundle.manifest.documents[name]:
            raise ValueError('HASH_MISMATCH')
    events = [TraceEvent.model_validate(e) for e in bundle.documents.get('events', [])]
    if [e.seq for e in events] != list(range(1, len(events) + 1)):
        raise ValueError('EVENT_SEQUENCE')
    if any(e.at < bundle.manifest.started_at or e.at > bundle.manifest.ended_at for e in events):
        raise ValueError('EVENT_TIME_RANGE')
    if any(a.at > b.at for a, b in zip(events, events[1:])):
        raise ValueError('EVENT_TIME_ORDER')
    return bundle


def import_bundle(bundle: ArtifactBundle, root: Path) -> ArtifactReceipt:
    raw = bundle.model_dump(mode='json')
    validate_bundle(raw)
    content = canonical(raw)
    content_digest = hashlib.sha256(content).hexdigest()
    directory = Path(root) / bundle.manifest.run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'bundle.json'
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.capture-')
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError('RUN_CONFLICT') from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return ArtifactReceipt(run_id=bundle.manifest.run_id, digest=content_digest, storage_key=f'{bundle.manifest.run_id}/bundle.json')
