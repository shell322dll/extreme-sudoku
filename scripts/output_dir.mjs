import os from 'node:os';
import path from 'node:path';

const norm = (value) => (process.platform === 'win32' ? value.toLowerCase() : value);
const inside = (child, parent) => norm(child).startsWith(norm(parent) + path.sep);

/** The build wipes its output directory, so only `<root>/dist` (or below) and sub-folders of the OS temp dir are allowed. */
export function resolveOutputDir(argument, root, tmp = os.tmpdir()) {
  const out = path.resolve(root, argument ?? 'dist');
  const dist = path.join(root, 'dist');
  if (norm(out) === norm(dist) || inside(out, dist) || inside(out, path.resolve(tmp))) return out;
  throw new Error(`Refusing to wipe ${out}: --out must be "dist", a sub-path of dist/, or a sub-folder of ${path.resolve(tmp)}.`);
}
