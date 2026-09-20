/**
 * Build script for dsh-tableware-radar.
 *
 * Produces three artifacts:
 *   lib/index.js       — host half, plain ESM the cordis loader imports by the patch row name.
 *   lib/typert.host.js — host TYPERT manifest (ESM, `zod` resolved from node_modules).
 *   lib/client.js      — browser half, wrapped in the DSH module-loader factory envelope
 *                        (`window.__ModuleLoader__.load`), `zod` bundled in.
 *
 * esbuild is located from the local install, then the global root, then the npx cache —
 * this machine cannot always reach the registry, so we never assume `npm install` succeeded.
 *
 * Run: node build.mjs   (or: npm run build / node scripts/dev.mjs)
 */
import { createRequire } from 'node:module'
import { mkdirSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const root = dirname(fileURLToPath(import.meta.url))

/** Resolve esbuild without touching the network. */
function resolveEsbuild() {
  try {
    return require('esbuild')
  } catch { /* not installed locally */ }

  const { execSync } = require('node:child_process')
  try {
    const globalRoot = execSync('npm root -g', { encoding: 'utf-8' }).trim()
    return require(join(globalRoot, 'esbuild'))
  } catch { /* not installed globally */ }

  const npxRoot = join(process.env.LOCALAPPDATA ?? '', 'npm-cache', '_npx')
  try {
    for (const dir of readdirSync(npxRoot)) {
      const candidate = join(npxRoot, dir, 'node_modules', 'esbuild')
      try {
        require.resolve(join(candidate, 'package.json'))
        return require(candidate)
      } catch { /* keep scanning */ }
    }
  } catch { /* no npx cache at all */ }

  throw new Error('esbuild not found — run: npm i -D esbuild')
}

const esbuild = resolveEsbuild()

mkdirSync(join(root, 'lib'), { recursive: true })

// ---- 1. client half: browser bundle in the module-loader envelope ----------
// Only react is external (resolved from the live module table); zod is bundled.
await esbuild.build({
  entryPoints: [join(root, 'src', 'client', 'index.js')],
  bundle: true,
  format: 'cjs',
  outfile: join(root, 'lib', 'client.js'),
  platform: 'browser',
  target: ['es2020'],
  external: ['react', 'react/jsx-runtime'],
  minify: false,
  sourcemap: false,
  banner: {
    js: 'window.__ModuleLoader__.load({ id: "dsh-tableware-radar", factory: (require) => {\n'
      + 'var module = { exports: {} };\nvar exports = module.exports;',
  },
  footer: {
    js: 'return module.exports; } });',
  },
})

// ---- 2. host half: ESM module for the cordis loader ------------------------
await esbuild.build({
  entryPoints: [join(root, 'src', 'index.js')],
  bundle: true,
  format: 'esm',
  outfile: join(root, 'lib', 'index.js'),
  platform: 'node',
  target: ['node20'],
  external: ['@deepseek-ai/cordis'],
  minify: false,
  sourcemap: false,
})

// ---- 3. host TYPERT manifest: ESM, zod resolved from the profile -----------
await esbuild.build({
  entryPoints: [join(root, 'src', 'typert.host.js')],
  bundle: true,
  format: 'esm',
  outfile: join(root, 'lib', 'typert.host.js'),
  platform: 'node',
  target: ['node20'],
  external: ['zod'],
  minify: false,
  sourcemap: false,
})

console.log('[dsh-tableware-radar] build ok: lib/index.js, lib/typert.host.js, lib/client.js')
