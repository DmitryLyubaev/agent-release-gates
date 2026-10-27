import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadSubject, hash, canonical } from './subject.mjs';
import { observeAudit, scriptedCase } from './observe.mjs';

export async function captureCase({subjectRoot,caseDefinition,script,subjectVersion,outputRoot,expectedCommit,mode='scripted',reviewSequence}) {
  if (mode !== 'scripted') throw new Error('LIVE_MODE_NOT_CONFIGURED');
  const subject = await loadSubject(subjectRoot,expectedCommit);
  const datasetBytes = await readFile('datasets/manifest.json');
  const fixtureBytes = await readFile(join('datasets',caseDefinition.fixture));
  const goldBytes = await readFile(join('datasets',caseDefinition.gold));
  if (hash(fixtureBytes)!==caseDefinition.fixture_digest || hash(goldBytes)!==caseDefinition.gold_digest) throw new Error('CASE_DIGEST');
  const fixture = JSON.parse(fixtureBytes), gold = JSON.parse(goldBytes);
  const started_at = new Date().toISOString(), events = [], raw_proposals = [];
  const emit = (kind,payload) => events.push({seq:events.length+1,at:new Date().toISOString(),kind,payload});
  const working = await mkdtemp(join(tmpdir(),'subject-run-'));
  const store = subject.openStore(working);
  const drain = observeAudit(store,emit);
  const systemPrompt=subject.LIVE_IDENTITY.systemPrompt+(subjectVersion==='candidate'?'\nDistinguish observed facts from possible causes, and give one evidence-bound next step.':'');
  const identity = {...subject.FAKE_IDENTITY, systemPrompt,modelVersion:'scripted-v1',promptVersion:subjectVersion};
  const fake = subject.createFakeModel(script ?? scriptedCase(fixture,caseDefinition.scenario));
  const model = {async next(input,signal) {
    drain(); emit('model_request', {turn:input.turn,messages:input.messages});
    try {
      const reply = await fake.next(input,signal);
      emit('model_response',{turn:input.turn,reply});
      if (reply.type === 'proposal') raw_proposals.push(structuredClone(reply.proposal));
      return reply;
    } catch(error) { emit('model_error',{turn:input.turn,code:error.message}); throw error; }
  }};
  let workflow, snapshot = null, proposal = null, status='failed', complete=false, error=null, final_sources=[];
  try {
    const imported = subject.importFixture(store, fixture);
    if (imported.status === 'rejected') throw new Error(imported.code);
    snapshot = subject.loadSnapshot(store,fixture.sources[0].batchId,fixture.sources[0].receiptId);
    workflow = subject.createWorkflow({store,live:{identity,adapter:model},applyIntent:(id,proposalId)=>subject.applyIntent(store,id,undefined,proposalId)});
    const view = await workflow.start(snapshot,{id:'unused',version:'1',steps:[]});
    drain(); status=view.status;
    if (view.proposalId) {
      proposal=JSON.parse(store.db.prepare('SELECT payload FROM proposals WHERE id=?').get(view.proposalId).payload);
      const command={proposalId:proposal.id,proposalVersion:proposal.version,snapshotDigest:proposal.snapshotDigest,idempotencyKey:'capture-review',decision:proposal.category==='explained_rounding'?'accept':'acknowledge'};
      const review=reviewSequence ?? gold.review_sequence;
      if (review === 'stale') {
        const changed=structuredClone(fixture); changed.sources[0].version++; changed.sources[0].notes='New synthetic evidence version.';
        subject.importFixture(store,changed);
      }
      if (review !== 'none') {
        emit('review_request',command);
        try {
          subject.recordDecision(store,command);
          if (review === 'accept_repeat') {
            const receipt=subject.recordDecision(store,command);
            if(receipt.replayed) emit('review_replayed',command);
          }
          await subject.recoverPending({store,workflow});
          await subject.recoverPending({store,workflow});
        } catch(cause) { emit('review_refused',{...command,code:cause.message}); }
        drain();
      }
    }
    complete=true;
  } catch(cause) { error=cause.message; }
  finally {
    drain();
    final_sources=store.db.prepare('SELECT payload FROM source_versions ORDER BY id,version').all().map(r=>JSON.parse(r.payload));
    if(workflow) await workflow.close();
    store.db.close();
    await rm(working,{recursive:true,force:true});
  }
  emit('capture_finished',{status,complete});
  const documents={evidence:snapshot,final_sources,proposal,events,raw_proposals,capture:{complete,status,error}};
  const adapterDigest=hash((await Promise.all(['capture.mjs','subject.mjs','observe.mjs','mutate.mjs'].map(f=>readFile(new URL(f,import.meta.url))))).map(b=>hash(b)).join(''));
  const manifest={schema_version:1,run_id:`run_${randomUUID()}`,case_id:caseDefinition.case_id,family_id:caseDefinition.family_id,split:caseDefinition.split,subject_version:subjectVersion,mode,subject_commit:subject.commit,source_digest:subject.sourceDigest,adapter_digest:adapterDigest,dataset_digest:hash(datasetBytes),
    settings:{model:identity.modelVersion,prompt:identity.promptVersion,prompt_digest:hash(identity.systemPrompt),compiled_digest:subject.compiledDigest,tools:'project13-locked'},started_at,ended_at:new Date().toISOString(),usage:{state:'not_incurred',input_tokens:0,output_tokens:0,cost_nano_usd:0,reserved_nano_usd:0,price_id:null},documents:Object.fromEntries(Object.entries(documents).map(([k,v])=>[k,hash(canonical(v))])),parent_digest:null,fault_recipe:null};
  const directory=join(outputRoot,manifest.run_id); await mkdir(directory,{recursive:true});
  await writeFile(join(directory,'bundle.json'),canonical({manifest,documents}),{flag:'wx'});
  return manifest;
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const {values}=parseArgs({options:{'subject-root':{type:'string',default:'.local/subject'},mode:{type:'string',default:'scripted'},split:{type:'string',default:'release'},output:{type:'string',default:'artifacts/scripted'},version:{type:'string',default:'baseline'}}});
  if(values.mode!=='scripted') throw new Error('LIVE_MODE_NOT_CONFIGURED');
  const manifest=JSON.parse(await readFile('datasets/manifest.json'));
  for(const caseDefinition of manifest.cases.filter(c=>c.split===values.split)) {
    const result=await captureCase({subjectRoot:resolve(values['subject-root']),caseDefinition,subjectVersion:values.version,outputRoot:values.output});
    console.log(JSON.stringify({case_id:result.case_id,run_id:result.run_id,mode:result.mode}));
  }
}
