import assert from 'node:assert/strict';
import { test } from 'node:test';
import { harness } from './live-support.mjs';
import { mutateBundle } from '../mutate.mjs';
import { createHash } from 'node:crypto';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';

globalThis.fetch=()=>{throw new Error('NETWORK_FORBIDDEN');};

test('stubbed provider uses real live subject and settles every recorded turn exactly once', async()=>{
  const h=await harness();
  try {
    const b=await h.capture();
    assert.equal(b.documents.capture.status,'awaiting_review');
    assert.ok(b.documents.proposal);
    assert.equal(b.manifest.mode,'live');
    assert.equal(b.manifest.usage.state,'known');
    assert.equal(b.manifest.usage.cost_nano_usd,1200000);
    assert.equal(h.calls,4);
    assert.equal(b.documents.provider_receipts.length,4);
    assert.equal(b.documents.provider_receipts[0].request.model,'claude-sonnet-5-5');
    assert.equal(b.documents.provider_receipts[0].response.usage.input_tokens,100);
    assert.equal(b.documents.provider_receipts[0].request.messages.length,1);
    assert.ok(!JSON.stringify(b).includes('test-secret-never-export'));
    assert.ok(!JSON.stringify(b).includes('x-api-key'));
    const derived=mutateBundle(b,'unsupported_cause');
    assert.equal(derived.manifest.usage.cost_nano_usd,1200000);
    assert.equal(derived.manifest.mode,'fault_control');
  } finally {await h.close();}
});

test('ambiguous network failure is retained, redacted and cannot send a retry', async()=>{
  const h=await harness();let sent=0;
  try {
    const b=await h.capture({transport:async()=>{sent++;throw new Error('test-secret-never-export account_id=private');}});
    assert.equal(sent,1);
    assert.equal(b.documents.capture.status,'failed');
    assert.equal(b.manifest.usage.state,'unknown');
    assert.equal(b.manifest.usage.reserved_nano_usd,2040960000);
    assert.equal(b.documents.provider_receipts[0].error,'PROVIDER_UNCERTAIN');
    assert.ok(!JSON.stringify(b).includes('test-secret-never-export'));
    assert.ok(!JSON.stringify(b).includes('account_id=private'));
  } finally {await h.close();}
});

test('bad provider reply still records its known usage and raw bounded content', async()=>{
  const h=await harness();
  try {
    const b=await h.capture({transport:async()=>new Response(JSON.stringify({id:'msg_bad',model:'claude-sonnet-5-5',stop_reason:'max_tokens',content:[{type:'text',text:'unfinished'}],usage:{input_tokens:100,output_tokens:10}}),{status:200})});
    assert.equal(b.documents.capture.status,'failed');
    assert.equal(b.manifest.usage.state,'known');
    assert.equal(b.documents.provider_receipts[0].response.content[0].text,'unfinished');
    assert.equal(b.manifest.usage.cost_nano_usd,300000);
  } finally {await h.close();}
});

test('approval or pin failure has no provider side effects', async()=>{
  const h=await harness();
  try {
    await assert.rejects(h.capture({approval:null}),/LIVE_MODE_NOT_CONFIGURED/);
    await assert.rejects(h.capture({expectedCommit:'0'.repeat(40)}),/SUBJECT_PIN/);
    assert.equal(h.calls,0);
  } finally {await h.close();}
});

for(const structured of [true,false])test(`HTTP error privacy covers ${structured?'JSON':'non-JSON'} diagnostics and durable journal`,async()=>{
  const h=await harness();
  const message='account acct_private_123 organization org_private_456 test-secret-never-export';
  const raw=structured?JSON.stringify({type:'error',id:'acct_private_123',error:{type:'permission_error',message}}):`<html>${message}</html>`;
  try {
    const b=await h.capture({transport:async()=>new Response(raw,{status:403})});
    assert.equal(b.documents.capture.status,'failed');
    assert.equal(b.manifest.usage.state,'unknown');
    const receipt=b.documents.provider_receipts[0];
    const exported=JSON.stringify(b);
    assert.ok(!exported.includes('acct_private_123'));
    assert.ok(!exported.includes('org_private_456'));
    assert.equal(receipt.response.http_status,403);
    assert.equal(receipt.response.body_sha256,createHash('sha256').update(raw).digest('hex'));
    assert.equal(receipt.response.body_bytes,Buffer.byteLength(raw));
    const directory=join(h.root,'captures/provider-receipts');
    const journal=await readFile(join(directory,(await readdir(directory))[0]),'utf8');
    assert.ok(!journal.includes('acct_private_123'));
    assert.ok(!journal.includes('org_private_456'));
  }finally{await h.close();}
});
