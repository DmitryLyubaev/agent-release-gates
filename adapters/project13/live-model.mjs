import { budgetOperation, recordedFetch } from './provider.mjs';

export function createLiveModel(options) {
  const {subject,approval,ledgerPath,pythonExecutable,transport,identity,investigationId,stage,receiptRoot,apiKey=process.env.ANTHROPIC_API_KEY}=options;
  if(!approval)throw new Error('LIVE_MODE_NOT_CONFIGURED');
  if(!approval.allowed_stages?.includes(stage))throw new Error('STAGE_NOT_APPROVED');
  if(!apiKey)throw new Error('ANTHROPIC_KEY_REQUIRED');
  const worker={approval,ledgerPath,pythonExecutable};
  budgetOperation(worker,'summary');
  const receipts=[];let reservationId;
  const budget={
    reserve({turn}) {
      reservationId=budgetOperation(worker,'reserve',{attempt_key:`${investigationId}:${turn}`,kind:'subject',investigation_id:investigationId,metadata:{stage,turn}});
      return reservationId;
    },
    settle(id,usage,requestId){return budgetOperation(worker,'settle',{reservation_id:id,usage,request_id:requestId});},
  };
  const adapter=subject.createAnthropicModel({apiKey,budget,transport:(url,init)=>recordedFetch({url,init,kind:'subject',reservationId,receipts,apiKey,transport,receiptRoot,projectRoot:approval.config.project_root})});
  return {
    identity,adapter,receipts,
    usageSummary() {
      const rows=budgetOperation(worker,'summary').calls.filter(row=>row.investigation===investigationId);
      const unknown=rows.some(row=>row.charge===null);
      return {state:unknown?'unknown':'known',input_tokens:rows.reduce((n,r)=>n+(r.usage?.input_tokens??0),0),output_tokens:rows.reduce((n,r)=>n+(r.usage?.output_tokens??0),0),cost_nano_usd:unknown?null:rows.reduce((n,r)=>n+r.charge,0),reserved_nano_usd:rows.filter(r=>r.charge===null).reduce((n,r)=>n+r.reserved,0),price_id:approval.config.price_id};
    },
  };
}
