import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { access, mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
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

test('the built page content-hashes the database and all app code URLs (stale Pages cache cannot mix versions)', async () => {
  const out = await mkdtemp(path.join(os.tmpdir(), 'es-build-hash-'));
  try {
    const run = spawnSync(process.execPath, [path.join(root, 'scripts', 'build_pages.mjs'), '--out', out], { encoding: 'utf8' });
    assert.equal(run.status, 0, run.stderr);
    const html = await readFile(path.join(out, 'index.html'), 'utf8');
    const published = await readFile(path.join(out, 'data', 'production', 'puzzles.json'));
    const match = html.match(/<meta name="puzzle-database" content="\.\/data\/production\/puzzles\.json\?v=([0-9a-f]{16})">/);
    assert.ok(match, 'meta tag must carry ?v=<hash>');
    assert.equal(match[1], createHash('sha256').update(published).digest('hex').slice(0, 16));
    assert.equal(JSON.parse(published).derived, true);

    // Application code: one content hash on the entry script, stylesheet, package.json and every relative import.
    const libs = (await readdir(path.join(root, 'web', 'lib'))).filter(name => name.endsWith('.js')).sort().map(name => `lib/${name}`);
    const hash = createHash('sha256');
    for (const file of ['app.js', 'styles.css', 'package.json', ...libs]) hash.update(`${file}\0`).update(await readFile(path.join(root, 'web', file))).update('\0');
    const v = hash.digest('hex').slice(0, 16);
    assert.ok(html.includes(`<script type="module" src="./app.js?v=${v}"></script>`), 'entry script hash');
    assert.ok(html.includes(`<link rel="stylesheet" href="./styles.css?v=${v}">`), 'stylesheet hash');
    let imports = 0;
    for (const file of ['app.js', ...libs]) {
      const code = await readFile(path.join(out, file), 'utf8');
      for (const [, specifier] of code.matchAll(/(?:\bfrom\s*|\bimport\s*\(\s*)['"](\.\.?\/[^'"]+)['"]/g)) {
        assert.ok(specifier.endsWith(`.js?v=${v}`), `${file}: ${specifier} is not content-hashed`);
        imports++;
      }
      // Only URLs change: stripping the queries restores the source byte for byte.
      assert.equal(code.replaceAll(`?v=${v}`, ''), await readFile(path.join(root, 'web', file), 'utf8'), `${file} changed beyond its URLs`);
    }
    assert.ok(imports >= 6, `expected the app's module imports to be rewritten, saw ${imports}`);
    assert.ok((await readFile(path.join(out, 'app.js'), 'utf8')).includes(`new URL('./package.json?v=${v}', import.meta.url)`), 'package.json (version label) hash');
    // The development page (web/) is untouched.
    assert.ok((await readFile(path.join(root, 'web', 'index.html'), 'utf8')).includes('<script type="module" src="./app.js"></script>'));
  } finally { await rm(out, { recursive: true, force: true }); }
});
