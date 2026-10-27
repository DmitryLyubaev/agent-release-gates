import { spawnSync } from 'node:child_process';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, delimiter } from 'node:path';
import { existsSync } from 'node:fs';
import { captureCase } from '../capture.mjs';
import { scriptedCase } from '../observe.mjs';
import { hash, canonical } from '../subject.mjs';

export const python = process.env.GATES_PYTHON_EXECUTABLE ?? resolve(existsSync('.venv/Scripts/python.exe') ? '.venv/Scripts/python.exe' : '.venv/bin/python');
export async function harness(options = {}) {
  const root = await mkdtemp(join(tmpdir(), 'live-stub-'));
  const approval = JSON.parse(spawnSync(python, ['-c', 'import json,sys; from pathlib import Path; from tests.live_support import allowance; print(json.dumps(allowance(Path(sys.argv[1]))))', root], {encoding:'utf8',env:{...process.env,PYTHONPATH:['src','.'].join(delimiter)}}).stdout);
  const dataset = await readFile('datasets/manifest.json');
  approval.config.dataset_digest = hash(dataset);
  approval.config_digest = hash(canonical(approval.config));
  const caseDefinition = JSON.parse(dataset).cases.find(c=>c.case_id===(options.caseId ?? 'c01'));
  const fixture = JSON.parse(await readFile(join('datasets',caseDefinition.fixture)));
  const script = scriptedCase(fixture,caseDefinition.scenario);
  let calls=0;
  const bodies=[];
  const transport = async (url,request) => {
    const body=JSON.parse(request.body); bodies.push(body);
    const step=script.steps[calls++];
    const content=step.type==='tools' ? step.calls.map(c=>({type:'tool_use',id:c.id,name:c.name,input:c.args})) : [{type:'tool_use',id:'submit',name:'submitProposal',input:step.proposal}];
    return new Response(JSON.stringify({id:'msg_test',type:'message',role:'assistant',model:'claude-sonnet-5-5',stop_reason:'tool_use',content,usage:{input_tokens:100,output_tokens:10}}),{status:200,headers:{'request-id':`req_test_${calls}`}});
  };
  return {
    root,approval,bodies,get calls(){return calls;},
    async capture(extra={}) {
      const result = await captureCase({subjectRoot:resolve('.local/subject'),caseDefinition,subjectVersion:'baseline',outputRoot:join(root,'captures'),mode:'live',approval,ledgerPath:approval.config.ledger_path,pythonExecutable:python,apiKey:'test-secret-never-export',transport,...extra});
      return JSON.parse(await readFile(join(root,'captures',result.run_id,'bundle.json')));
    },
    async close(){await rm(root,{recursive:true,force:true});},
  };
}
