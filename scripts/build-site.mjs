import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

// Publish an explicit allowlist of tracked files; never raw local sources or server code.
const output = resolve('.netlify/site');
rmSync(output, { recursive: true, force: true });
const files = execFileSync('git', ['ls-files', '-z'], { encoding: 'utf8' }).split('\0')
  .filter(path => ['index.html', 'data.json', 'course-outcomes.json', 'site-edits.json'].includes(path) || path.startsWith('assets/'));
for (const path of files) {
  const target = resolve(output, path);
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(path, target);
}
console.log(`Prepared ${files.length} tracked public files.`);
