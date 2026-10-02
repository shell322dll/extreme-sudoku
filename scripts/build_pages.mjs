// Build the static GitHub Pages site: web/ + data/production/puzzles.json -> dist/ (or --out DIR).
//
//   node scripts/build_pages.mjs [--out dist]
//
// The published JSON is derived from the production database here (proof evidence and config are
// dropped, a compact hardestStep is added), so there is never a hand-maintained second copy.
// Every URL stays relative: the site works at https://<user>.github.io/<repo>/ and at any other prefix.
import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveOutputDir } from './output_dir.mjs';
import { parseProductionDatabase, slimDatabase } from '../web/lib/data.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
if (args.length && !(args.length === 2 && args[0] === '--out' && args[1])) throw new Error('Usage: node scripts/build_pages.mjs [--out DIR]');
const out = resolveOutputDir(args[1], root);

const DATABASE_SOURCE = path.join(root, 'data', 'production', 'puzzles.json');
const DATABASE_TARGET = 'data/production/puzzles.json';
const PUBLISHED = ['index.html', 'styles.css', 'app.js', 'package.json'];
const META_SOURCE = '<meta name="puzzle-database" content="../data/production/puzzles.json">';
const META_TARGET = `<meta name="puzzle-database" content="./${DATABASE_TARGET}">`;

const database = JSON.parse((await readFile(DATABASE_SOURCE, 'utf8')).replace(/^﻿/, ''));
const playable = parseProductionDatabase(database, (...details) => console.warn('build:', ...details));
if (playable.length !== database.puzzles.length) {
  throw new Error(`Refusing to publish: ${database.puzzles.length - playable.length} record(s) are invalid or not certified. Run scripts/validate_production_database.py.`);
}
if (!playable.length) console.warn('build: the production database is empty; the site will show "no certified puzzles".');

await rm(out, { recursive: true, force: true });
await mkdir(path.join(out, 'data', 'production'), { recursive: true });
for (const file of PUBLISHED) await cp(path.join(root, 'web', file), path.join(out, file));
await cp(path.join(root, 'web', 'lib'), path.join(out, 'lib'), { recursive: true });

const indexPath = path.join(out, 'index.html');
const html = await readFile(indexPath, 'utf8');
if (html.split(META_SOURCE).length !== 2) throw new Error('web/index.html must contain the puzzle-database meta tag exactly once.');
await writeFile(indexPath, html.replace(META_SOURCE, META_TARGET));
await writeFile(path.join(out, DATABASE_TARGET), `${JSON.stringify(slimDatabase(database))}\n`);
await writeFile(path.join(out, '.nojekyll'), '');

// Fail on anything a project sub-path would break: root-absolute or scheme-relative URLs in published code.
const walk = async (dir) => (await Promise.all((await readdir(dir, { withFileTypes: true })).map((entry) => entry.isDirectory() ? walk(path.join(dir, entry.name)) : [path.join(dir, entry.name)]))).flat();
const offenders = [];
for (const file of (await walk(out)).filter((name) => /\.(html|css|js)$/.test(name))) {
  const text = await readFile(file, 'utf8');
  for (const pattern of [/\b(?:src|href|action)\s*=\s*["']\/[^"']/g, /url\(\s*["']?\/[^)]/g, /\bfrom\s+["']\//g, /\bimport\s*\(\s*["']\//g, /fetch\(\s*["']\//g]) {
    for (const match of text.matchAll(pattern)) offenders.push(`${path.relative(out, file)}: ${match[0]}`);
  }
}
if (offenders.length) throw new Error(`Root-absolute URLs would break GitHub Pages sub-paths:\n${offenders.join('\n')}`);

const size = async (file) => (await stat(path.join(out, file))).size;
console.log(`Built ${path.relative(root, out) || out}: ${playable.length} certified puzzle(s); ${DATABASE_TARGET} ${await size(DATABASE_TARGET)} bytes (source ${(await stat(DATABASE_SOURCE)).size} bytes).`);
