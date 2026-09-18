/**
 * Build script for dsh-plugin-workbench.
 *
 * Produces two bundles:
 *   client/client.js — the browser half, wrapped in the DSH module-loader
 *                      factory envelope (window.__ModuleLoader__.load).
 *   lib/index.js     — the host half, a plain ESM module the cordis loader
 *                      imports by the name our cordis.patch.yml row declares.
 *
 * esbuild is located from the local install, then the global root, then the
 * npx cache — this machine cannot always reach the registry, so we never
 * assume a fresh `npm install` succeeded.
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

mkdirSync(join(root, 'client'), { recursive: true })
mkdirSync(join(root, 'lib'), { recursive: true })

// ---- 1. client half: browser bundle in the module-loader envelope ----------
// The loader hands us `require`; react is the only external, resolved from the
// live module table, so the bundle stays small and version-agnostic.
await esbuild.build({
  entryPoints: [join(root, 'src', 'client', 'index.ts')],
  bundle: true,
  format: 'cjs',
  outfile: join(root, 'client', 'client.js'),
  platform: 'browser',
  target: ['es2020'],
  external: ['react', 'react/jsx-runtime'],
  minify: false,
  sourcemap: false,
  banner: {
    js: 'window.__ModuleLoader__.load({ id: "dsh-plugin-workbench", factory: (require) => {\n'
      + 'var module = { exports: {} };\nvar exports = module.exports;',
  },
  footer: {
    js: 'return module.exports; } });',
  },
})

// ---- 2. host half: ESM module for the cordis loader ------------------------
// The cordis runtime is supplied by the DSH host at load time.
await esbuild.build({
  entryPoints: [join(root, 'src', 'index.ts')],
  bundle: true,
  format: 'esm',
  outfile: join(root, 'lib', 'index.js'),
  platform: 'node',
  target: ['node20'],
  external: ['@deepseek-ai/cordis'],
  minify: false,
  sourcemap: false,
})

console.log('[dsh-plugin-workbench] build ok: lib/index.js, client/client.js')
