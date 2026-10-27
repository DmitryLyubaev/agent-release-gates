import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { captureCase } from '../capture.mjs';
import { mutateBundle } from '../mutate.mjs';

globalThis.fetch = () => { throw new Error('NETWORK_FORBIDDEN'); };
const subjectRoot = resolve('.local/subject');
async function capture(id, extra = {}) {
  const outputRoot = await mkdtemp(join(tmpdir(), 'gate-capture-'));
  try {
    const manifest = JSON.parse(await readFile('datasets/manifest.json', 'utf8'));
    const caseDefinition = manifest.cases.find(c => c.case_id === id);
    const result = await captureCase({ subjectRoot, caseDefinition, subjectVersion: 'baseline', outputRoot, ...extra });
    return JSON.parse(await readFile(join(outputRoot, result.run_id, 'bundle.json'), 'utf8'));
  } finally { await rm(outputRoot, {recursive: true, force: true}); }
}

test('capture real workflow, record tool/model evidence and one outcome under repeated review', async () => {
  const first = await capture('r01'), second = await capture('r01');
  assert.notEqual(first.manifest.run_id, second.manifest.run_id);
  assert.notEqual(first.documents.proposal.id, second.documents.proposal.id);
  const events = first.documents.events;
  assert.equal(events.filter(e => e.kind === 'outcome').length, 1);
  assert.equal(events.filter(e => e.kind === 'review_replayed').length, 1);
  assert.ok(events.findIndex(e => e.kind === 'review_request') < events.findIndex(e => e.kind === 'outcome'));
  assert.ok(events.some(e => e.kind === 'model_request' && e.payload.messages));
  assert.ok(events.some(e => e.kind === 'tool_result' && e.payload.name === 'getEvidence'));
  assert.equal(first.documents.proposal.differenceMinor, '1');
  assert.equal(first.documents.capture.complete, true);
  assert.equal(first.manifest.usage.state, 'not_incurred');
});

test('stale evidence refuses old approval despite injected safe=true note', async () => {
  const captured = await capture('r04');
  assert.ok(captured.documents.events.some(e => e.kind === 'review_refused' && e.payload.code === 'STALE'));
  assert.equal(captured.documents.events.filter(e => e.kind === 'outcome').length, 0);
  assert.ok(captured.documents.evidence.sources[0].notes.includes('safe=true'));
});

test('no-review run has no terminal outcome', async () => {
  const raw = await capture('r01', { reviewSequence: 'none' });
  assert.equal(raw.documents.events.some(e => e.kind === 'outcome'), false);
});

test('failed or rejected raw model proposals retained', async () => {
  const raw = await capture('r01', { script: { id: 'broken', version: '1', steps: [{type:'proposal', proposal:{explanation:'Unsupported raw claim'}}] } });
  assert.equal(raw.documents.capture.status, 'failed');
  assert.equal(raw.documents.raw_proposals[0].explanation, 'Unsupported raw claim');
  assert.ok(raw.documents.events.some(e => e.kind === 'proposal_rejected'));
});

test('pin mismatch and live mode refuse before network', async () => {
  await assert.rejects(capture('r01', {expectedCommit:'0'.repeat(40)}), /SUBJECT_PIN/);
  await assert.rejects(capture('r01', {mode:'live'}), /LIVE_MODE_NOT_CONFIGURED/);
});

test('fault controls retain parent and separate semantic from exact faults', async () => {
  const original = await capture('r01');
  const semantic = mutateBundle(original, 'unsupported_cause');
  const unsafe = mutateBundle(original, 'change_money');
  assert.equal(semantic.manifest.mode, 'fault_control');
  assert.equal(original.manifest.mode, 'scripted');
  assert.ok(semantic.manifest.parent_digest);
  assert.equal(semantic.documents.proposal.differenceMinor, original.documents.proposal.differenceMinor);
  assert.notEqual(semantic.documents.proposal.explanation, original.documents.proposal.explanation);
  assert.notEqual(unsafe.documents.final_sources[0].grossMinor, original.documents.final_sources[0].grossMinor);
});

test('candidate records a genuinely changed prompt identity', async () => {
  const baseline=await capture('r01');
  const candidate=await capture('r01',{subjectVersion:'candidate'});
  assert.notEqual(baseline.manifest.settings.prompt_digest,candidate.manifest.settings.prompt_digest);
});
