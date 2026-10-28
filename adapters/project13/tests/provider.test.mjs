import { test } from 'node:test';
import assert from 'node:assert/strict';
import { harness,python } from './live-support.mjs';
import { judgeMessage,budgetOperation } from '../provider.mjs';

globalThis.fetch=()=>{throw new Error('NETWORK_FORBIDDEN');};
const body={model:'claude-sonnet-5-5',max_tokens:1024,thinking:{type:'between_tools'},output_config:{effort:'low',format:{type:'json_schema',schema:{type:'object',properties:{},additionalProperties:false}}},system:'Use only the supplied evidence.',messages:[{role:'user',content:'synthetic evidence'}]};

test('live dispatch refuses an environment that disables TLS verification',async()=>{
  const h=await harness();const previous=process.env.NODE_TLS_REJECT_UNAUTHORIZED;let sent=0;
  try {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED='0';
    await assert.rejects(judgeMessage({approval:h.approval,ledgerPath:h.approval.config.ledger_path,pythonExecutable:python,attemptKey:'tls-test',stage:'calibration',apiKey:'test-key',body,transport:async()=>{sent++;throw new Error('must not send');}}),/TLS_VERIFICATION_REQUIRED/);
    assert.equal(sent,0);
  }finally{if(previous===undefined)delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;else process.env.NODE_TLS_REJECT_UNAUTHORIZED=previous;await h.close();}
});

test('unpriced request is refused before reservation or network dispatch',async()=>{
  const h=await harness();let sent=0;
  try {
    const options={approval:h.approval,ledgerPath:h.approval.config.ledger_path,pythonExecutable:python,attemptKey:'judge-1',stage:'calibration',apiKey:'test-judge-key',transport:async()=>{sent++;throw new Error('must not send');}};
    await assert.rejects(judgeMessage({...options,body:{...body,temperature:0}}),/UNPRICED_REQUEST/);
    assert.equal(sent,0);
    assert.equal(budgetOperation(options,'summary').calls.length,0);
  }finally{await h.close();}
});

test('judge enforces response model identity and preserves its priced receipt',async()=>{
  const h=await harness();
  try {
    const result=await judgeMessage({approval:h.approval,ledgerPath:h.approval.config.ledger_path,pythonExecutable:python,attemptKey:'judge-model',stage:'calibration',apiKey:'test-judge-key',body,transport:async()=>new Response(JSON.stringify({id:'msg_test',model:'unexpected-model',stop_reason:'end_turn',content:[],usage:{input_tokens:100,output_tokens:10}}),{status:200})});
    assert.equal(result.receipts[0].error,'PROVIDER_MODEL_MISMATCH');
    assert.equal(result.summary.spent_nano_usd,300000);
  }finally{await h.close();}
});
