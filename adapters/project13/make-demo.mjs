import { mkdir,readFile,writeFile } from 'node:fs/promises';
import { join,resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { captureCase } from './capture.mjs';
import { mutateBundle } from './mutate.mjs';
import { canonical } from './subject.mjs';

const {values}=parseArgs({options:{output:{type:'string',default:'examples/scripted'},'subject-root':{type:'string',default:'.local/subject'}}});
const output=resolve(values.output);
await mkdir(resolve(output,'..'),{recursive:true});
await mkdir(output); // A frozen example directory is never silently overwritten.
const dataset=JSON.parse(await readFile('datasets/manifest.json'));
const index={mode:'scripted',generated_at:new Date().toISOString(),versions:{baseline:[],candidate:[],exact_fault:[],semantic_fault:[]},review:{calibration:[],heldout:[]},judge_script:{}};
const verdict=accept=>({support:accept?'yes':'no',usefulness:accept?'yes':'no',evidence_ids:[],reason:accept?'Authored scripted supported example.':'Authored scripted unsupported or unsafe example.'});
async function saveControl(bundle,recipe) {
  const derived=mutateBundle(bundle,recipe);
  await mkdir(join(output,derived.manifest.run_id));
  await writeFile(join(output,derived.manifest.run_id,'bundle.json'),canonical(derived));
  return derived.manifest.run_id;
}
for(const definition of dataset.cases) {
  const base=await captureCase({subjectRoot:resolve(values['subject-root']),caseDefinition:definition,subjectVersion:'baseline',outputRoot:output});
  const bundle=JSON.parse(await readFile(join(output,base.run_id,'bundle.json')));
  index.judge_script[base.run_id]=verdict(true);
  if(definition.split==='release') {
    index.versions.baseline.push(base.run_id);
    const candidate=await captureCase({subjectRoot:resolve(values['subject-root']),caseDefinition:definition,subjectVersion:'candidate',outputRoot:output});
    index.versions.candidate.push(candidate.run_id);index.judge_script[candidate.run_id]=verdict(true);
    const raw=JSON.parse(await readFile(join(output,candidate.run_id,'bundle.json')));
    for(const [group,recipe] of [['exact_fault','change_money'],['semantic_fault','unsupported_cause']]) {
      const id=await saveControl(raw,recipe);index.versions[group].push(id);index.judge_script[id]=verdict(false);
    }
  } else {
    const control=dataset.review_items.find(i=>i.case_id===definition.case_id&&i.mutation);
    const id=await saveControl(bundle,control.mutation);
    index.review[definition.split].push(base.run_id,id);index.judge_script[id]=verdict(false);
  }
}
for(const item of dataset.review_items) index.judge_script[item.item_id]=verdict(item.mutation===null);
await writeFile(join(output,'index.json'),JSON.stringify(index,null,2)+'\n');
await writeFile(join(output,'judge.json'),JSON.stringify(index.judge_script,null,2)+'\n');
console.log(JSON.stringify({mode:'scripted',natural_runs:20,controls:20,human_labels:0,output:values.output}));
