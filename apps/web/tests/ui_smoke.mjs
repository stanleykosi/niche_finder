import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(new URL('..', import.meta.url).pathname);
for (const file of ['app/page.tsx', 'app/research/new/page.tsx', 'app/runs/[id]/page.tsx', 'app/runs/[id]/niches/[candidateId]/page.tsx', 'lib/api.ts', 'lib/schemas.ts', 'app/globals.css']) {
  assert.equal(fs.existsSync(path.join(root, file)), true, `missing frontend file ${file}`);
}
const css = fs.readFileSync(path.join(root, 'app/globals.css'), 'utf8');
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /@media \(max-width: 560px\)/);
console.log('frontend smoke checks: PASS');

