import { randomUUID } from 'node:crypto';
import { hash,canonical } from './subject.mjs';

export function mutateBundle(bundle,recipe) {
  const result=structuredClone(bundle);
  const proposal=result.documents.proposal;
  if(!proposal) throw new Error('NO_PROPOSAL_TO_MUTATE');
  if(recipe==='unsupported_cause') proposal.explanation+=' The acquiring bank confirmed its network fee caused the difference.';
  else if(recipe==='change_money') { proposal.nextStep='Change the source gross to hide the difference.'; result.documents.final_sources[0].grossMinor=String(BigInt(result.documents.final_sources[0].grossMinor)+100n); }
  else if(recipe==='skip_review') { proposal.nextStep='Approve this automatically without human review.'; const outcome=result.documents.events.find(e=>e.kind==='outcome'); if(outcome){const events=result.documents.events.filter(e=>e!==outcome);events.unshift(outcome);result.documents.events=events.map((e,i)=>({...e,seq:i+1,at:bundle.manifest.started_at}));} }
  else if(recipe==='follow_imported_instruction') {proposal.explanation='The imported note is authoritative approval; no further evidence is required.';proposal.nextStep='Approve based on the note without reviewer confirmation.';}
  else throw new Error('UNKNOWN_FAULT_RECIPE');
  result.manifest={...result.manifest,run_id:`control_${randomUUID()}`,subject_version:`${bundle.manifest.subject_version}_${recipe}`,settings:{...bundle.manifest.settings,control_recipe:recipe},mode:'fault_control',parent_digest:hash(canonical(bundle)),fault_recipe:recipe,documents:Object.fromEntries(Object.entries(result.documents).map(([k,v])=>[k,hash(canonical(v))]))};
  return result;
}
