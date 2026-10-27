export function observeAudit(store, emit) {
  let last = 0;
  return () => {
    for (const row of store.db.prepare('SELECT * FROM audit_events WHERE seq>? ORDER BY seq').all(last)) {
      last = row.seq;
      const payload = JSON.parse(row.body);
      const kind = {tool_result:'tool_result',proposal_saved:'proposal_saved',terminal_outcome:'outcome',investigation_failed:'proposal_rejected'}[row.type];
      if (kind) emit(kind === 'tool_result' && payload.result?.error ? 'tool_error' : kind, payload);
    }
  };
}

export function scriptedCase(fixture, scenario) {
  const refs = [...fixture.sources.map(s => ({kind:'source',id:s.id,version:s.version})), ...fixture.policies.map(p => ({kind:'policy',id:p.id,version:p.version}))];
  const source = name => fixture.sources.find(s => s.source === name);
  const category = scenario === 'missing' ? 'insufficient_evidence' : scenario === 'contradictory' ? 'contradictory_evidence' : 'explained_rounding';
  const steps = [
    {type:'tools', calls:[{id:'list',name:'listEvidence',args:{}}]},
    {type:'tools', calls:refs.map((ref,n) => ({id:`read_${n}`,name:'getEvidence',args:ref}))},
  ];
  const calculationIds = [];
  if (category === 'explained_rounding') steps.push({type:'tools',calls:fixture.sources.map((s,n) => {
    const rounding = fixture.policies.find(p => p.source === s.source).rounding;
    calculationIds.push(`${s.id}-v${s.version}-${rounding}`);
    return {id:`calc_${n}`,name:'compareRounding',args:{sourceRef:{kind:'source',id:s.id,version:s.version},rounding}};
  })});
  steps.push({type:'proposal', proposal:{id:'scripted', version:1, snapshotDigest:'',category,
    differenceMinor:String(BigInt(source('pos').grossMinor)-BigInt(source('accounting').grossMinor)),
    evidenceRefs:refs, calculationIds,
    explanation:category === 'explained_rounding' ? `The recorded totals in ${source('pos').id} and ${source('accounting').id}, version 1, differ by one cent under the supplied rounding profiles.` : category === 'insufficient_evidence' ? 'Item detail is missing; the cause of the recorded difference is not established.' : 'Recorded subtotal, tax and gross are contradictory; the cause cannot be attributed to rounding.',
    nextStep:category === 'explained_rounding' ? 'Ask a reviewer to inspect the cited records and calculations.' : 'Keep this exception open and request the missing or corrected source evidence.',
    modelVersion:'scripted-v1',promptVersion:'baseline'}});
  return {id:'synthetic-script',version:'1',steps};
}
