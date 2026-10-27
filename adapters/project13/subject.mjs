import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile,readdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const hash = value => createHash('sha256').update(value).digest('hex');
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
export async function compiledIdentity(root) {
  const files={};
  async function walk(relative='') {
    for(const entry of await readdir(resolve(root,'dist',relative),{withFileTypes:true})) {
      const name=relative?relative+'/'+entry.name:entry.name;
      if(name==='ui')continue;
      if(entry.isDirectory())await walk(name);
      else if(/\.(js|sql)$/.test(name))files[name]=hash((await readFile(resolve(root,'dist',name),'utf8')).replaceAll('\r\n','\n'));
    }
  }
  await walk();
  return hash(canonical(files));
}
export async function loadSubject(root, expectedCommit) {
  const lock = JSON.parse(await readFile(new URL('../../subject-lock.json', import.meta.url)));
  const git = args => execFileSync('git', ['-C', root, ...args], {encoding: 'utf8'}).trim();
  if (git(['rev-parse','HEAD']) !== (expectedCommit ?? lock.commit)) throw new Error('SUBJECT_PIN');
  if (git(['status','--porcelain','--untracked-files=no'])) throw new Error('SUBJECT_DIRTY');
  const sourceDigest = hash(git(['ls-tree','-r','HEAD']));
  if (sourceDigest !== lock.source_digest) throw new Error('SUBJECT_SOURCE_DIGEST');
  const compiledDigest=await compiledIdentity(root);
  if(compiledDigest!==lock.compiled_digest)throw new Error('COMPILED_SUBJECT_MISMATCH');
  const load = path => import(pathToFileURL(resolve(root, 'dist', path)).href);
  return { sourceDigest, compiledDigest,commit: lock.commit,
    ...await load('workflow/graph.js'), ...await load('workflow/decisions.js'),
    ...await load('workflow/runner.js'), ...await load('storage/store.js'),
    ...await load('storage/imports.js'), ...await load('investigation/fake-model.js'),
    ...await load('investigation/live-config.js'), ...await load('investigation/anthropic-model.js') };
}
