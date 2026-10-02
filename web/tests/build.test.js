import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolveOutputDir } from '../../scripts/output_dir.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

test('build output directory is allow-listed to dist/ or the OS temp dir', () => {
  assert.equal(resolveOutputDir(undefined, root), path.join(root, 'dist'));
  assert.equal(resolveOutputDir('dist/site', root), path.join(root, 'dist', 'site'));
  const tmp = path.join(os.tmpdir(), 'es-build-check');
  assert.equal(resolveOutputDir(tmp, root), tmp);
  for (const bad of ['data/production', 'data', 'generator', 'docs', 'scripts', 'web', '.', '..', 'dist/../data', root, os.tmpdir(), path.dirname(os.tmpdir()), 'distillery']) {
    assert.throws(() => resolveOutputDir(bad, root), /Refusing/, bad);
  }
});

test('the build CLI refuses a protected --out and leaves the files alone', async () => {
  const run = spawnSync(process.execPath, [path.join(root, 'scripts', 'build_pages.mjs'), '--out', 'data/production'], { encoding: 'utf8' });
  assert.notEqual(run.status, 0);
  assert.match(run.stderr, /Refusing/);
  await access(path.join(root, 'data', 'production', 'puzzles.json'));
});
