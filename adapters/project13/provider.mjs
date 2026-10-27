import { spawnSync } from 'node:child_process';
import { resolve, delimiter } from 'node:path';
import { relative, isAbsolute, join, dirname, basename } from 'node:path';
import { mkdirSync,realpathSync,existsSync,openSync,writeFileSync,fsyncSync,closeSync,renameSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export const ENDPOINT='https://api.anthropic.com/v1/messages';
export function budgetOperation({approval,ledgerPath,pythonExecutable},operation,args={}) {
  const env={...process.env,PYTHONPATH:[resolve('src'),resolve('.')].join(delimiter)};
  delete env.ANTHROPIC_API_KEY;
  const result=spawnSync(pythonExecutable,['-m','agent_release_gates.live.budget_worker'],{
    input:JSON.stringify({approval,path:ledgerPath,operation,arguments:args}),encoding:'utf8',env,maxBuffer:1048576,timeout:30000,
  });
  let reply;
  try {reply=JSON.parse(result.stdout);}catch{throw new Error('BUDGET_UNAVAILABLE');}
  if(!reply.ok)throw new Error(/^[A-Z_]+$/.test(reply.error)?reply.error:'BUDGET_UNAVAILABLE');
  return reply.value;
}

export function redact(value,key='',secret=process.env.ANTHROPIC_API_KEY) {
  if(/authorization|api[_-]?key|headers|account|organization|workspace/i.test(key))return '[REDACTED]';
  if(typeof value==='string') {
    return secret ? value.replaceAll(secret,'[REDACTED]') : value;
  }
  if(Array.isArray(value))return value.map(v=>redact(v,'',secret));
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,redact(v,k,secret)]));
  return value;
}

export function validateRequest(body,kind) {
  const keys=['model','max_tokens','thinking','output_config','tools','tool_choice','system','messages'];
  if(Object.keys(body).some(k=>!keys.includes(k)) || body.model!=='claude-sonnet-5-5' || body.max_tokens!==(kind==='subject'?4096:1024))throw new Error('UNPRICED_REQUEST');
  if(body.thinking?.type!=='between_tools'||Object.keys(body.thinking).length!==1||body.output_config?.effort!=='low'||Object.keys(body.output_config).some(k=>!['effort','format'].includes(k)))throw new Error('UNPRICED_REQUEST');
  function check(value) {
    if(value&&typeof value==='object')for(const [key,item] of Object.entries(value)) {
      if(key==='cache_control')throw new Error('UNPRICED_REQUEST');
      check(item);
    }
  }
  check(body);
  if(kind==='judge' && (body.tools||body.tool_choice))throw new Error('UNPRICED_REQUEST');
  if(kind==='subject'&&(!Array.isArray(body.tools)||body.tools.some(t=>t.type||!['listEvidence','getEvidence','compareRounding','submitProposal'].includes(t.name))))throw new Error('UNPRICED_REQUEST');
  if(Buffer.byteLength(JSON.stringify(body))>262144)throw new Error('PROVIDER_INPUT_LIMIT');
}

export async function recordedFetch({url,init,kind,reservationId,receipts,apiKey,transport=fetch,receiptRoot,projectRoot}) {
  if(url!==ENDPOINT || init.method!=='POST')throw new Error('PROVIDER_ENDPOINT');
  const request=JSON.parse(init.body); validateRequest(request,kind);
  const clean=value=>JSON.parse(JSON.stringify(redact(value)).replaceAll(apiKey,'[REDACTED]'));
  const receipt={reservation_id:reservationId,request:clean(request),response:null,request_id:null,error:null,started_at:new Date().toISOString(),ended_at:null};
  receipts.push(receipt);
  const persist=()=>{
    if(!receiptRoot)return;
    const base=realpathSync.native(projectRoot);
    let ancestor=resolve(receiptRoot);const missing=[];
    while(!existsSync(ancestor)){missing.unshift(basename(ancestor));ancestor=dirname(ancestor);}
    const target=resolve(realpathSync.native(ancestor),...missing);
    if(relative(base,target).startsWith('..')||isAbsolute(relative(base,target)))throw new Error('RECEIPT_PATH');
    mkdirSync(target,{recursive:true});
    const actual=realpathSync.native(target);
    if(relative(base,actual).startsWith('..')||isAbsolute(relative(base,actual)))throw new Error('RECEIPT_PATH');
    const temporary=join(actual,`${reservationId}.${randomUUID()}.tmp`);
    const fd=openSync(temporary,'wx');
    try{writeFileSync(fd,JSON.stringify(receipt));fsyncSync(fd);}finally{closeSync(fd);}
    renameSync(temporary,join(actual,`${reservationId}.json`));
  };
  try {
    persist();
    const signal=init.signal?AbortSignal.any([init.signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000);
    const response=await transport(ENDPOINT,{...init,redirect:'error',signal});
    const reader=response.body?.getReader(); if(!reader)throw new Error('NO_RESPONSE_BODY');
    const chunks=[];let size=0;
    while(true) {
      const {done,value}=await reader.read();if(done)break;
      size+=value.byteLength;
      if(size>131072){await reader.cancel();throw new Error('RESPONSE_LIMIT');}
      chunks.push(value);
    }
    const text=Buffer.concat(chunks).toString('utf8');
    let body;try{body=JSON.parse(text);}catch{body={invalid_json_text:text};}
    receipt.response=clean(body);
    const requestId=String(response.headers.get('request-id')??body.id??'unavailable');
    receipt.request_id=/^[A-Za-z0-9_-]{1,200}$/.test(requestId)?requestId:'unavailable';
    receipt.ended_at=new Date().toISOString();
    persist();
    return new Response(text,{status:response.status,headers:{'request-id':receipt.request_id}});
  } catch {
    receipt.error='PROVIDER_UNCERTAIN';receipt.ended_at=new Date().toISOString();
    try{persist();}catch{/* never dispatch when the receipt cannot be persisted */}
    throw new Error('PROVIDER_UNCERTAIN');
  }
}

export async function judgeMessage(options) {
  const {approval,body,attemptKey,stage,apiKey=process.env.ANTHROPIC_API_KEY,transport}=options;
  if(!apiKey)throw new Error('ANTHROPIC_KEY_REQUIRED');
  validateRequest(body,'judge');
  const reservationId=budgetOperation(options,'reserve',{attempt_key:attemptKey,kind:'judge',investigation_id:null,metadata:{stage,request_digest:options.requestDigest}});
  const receipts=[];
  try {
    const response=await recordedFetch({url:ENDPOINT,init:{method:'POST',body:JSON.stringify(body),headers:{'content-type':'application/json','anthropic-version':'2023-06-01','x-api-key':apiKey}},kind:'judge',reservationId,receipts,apiKey,transport,receiptRoot:options.receiptRoot??join(approval.config.project_root,'artifacts/live',approval.config.study_id,'provider'),projectRoot:approval.config.project_root});
    const raw=JSON.parse(await response.text());
    if(!response.ok)throw new Error('PROVIDER_RESPONSE');
    budgetOperation(options,'settle',{reservation_id:reservationId,usage:raw.usage,request_id:receipts[0].request_id});
    if(raw.model!==approval.config.model)receipts[0].error='PROVIDER_MODEL_MISMATCH';
  }catch{if(receipts[0])receipts[0].error=receipts[0].error??'PROVIDER_INVALID_OR_UNPRICED';}
  return {receipts,summary:budgetOperation(options,'summary'),reservation_id:reservationId,model:approval.config.model};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  try {
    let text='';for await(const chunk of process.stdin){text+=chunk;if(Buffer.byteLength(text)>524288)throw new Error('INPUT_LIMIT');}
    const value=await judgeMessage(JSON.parse(text));
    process.stdout.write(JSON.stringify({ok:true,value}));
  }catch(error){process.stdout.write(JSON.stringify({ok:false,error:/^[A-Z_]+$/.test(error.message)?error.message:'PROVIDER_FAILED'}));process.exitCode=2;}
}
