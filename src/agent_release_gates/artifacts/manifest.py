import hashlib
import json
from pathlib import Path

from agent_release_gates.contracts.datasets import DatasetManifest, ExpectedCase


def load_dataset(root: Path | str) -> DatasetManifest:
    root = Path(root).resolve()
    manifest = DatasetManifest.model_validate_json((root / 'manifest.json').read_bytes())
    for case in manifest.cases:
        for name in ['fixture', 'gold']:
            path = (root / getattr(case, name)).resolve()
            if not path.is_relative_to(root):
                raise ValueError('DATASET_PATH')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != getattr(case, name + '_digest'):
                raise ValueError('DATASET_HASH')
            if name == 'gold':
                gold = ExpectedCase.model_validate(json.loads(data))
                if (gold.case_id, gold.family_id, gold.split) != (case.case_id, case.family_id, case.split):
                    raise ValueError('GOLD_IDENTITY')
    return manifest
