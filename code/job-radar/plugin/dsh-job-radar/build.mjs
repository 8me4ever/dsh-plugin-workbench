/**
 * Build script for dsh-job-radar.
 * Uses esbuild from the npx cache (avoid registry download on unstable
 * office network). Run: node build.mjs
 */
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const root = dirname(fileURLToPath(import.meta.url))

// Locate esbuild: try local, then the npx cache.
function resolveEsbuild() {
  try {
    return require('esbuild')
  } catch {
    const { execSync } = require('node:child_process')
    const out = execSync('npm root -g', { encoding: 'utf-8' }).trim()
    try {
      return require(join(out, 'esbuild'))
    } catch {
      // npx cache scan
      const { readdirSync } = require('node:fs')
      const npxRoot = join(process.env.LOCALAPPDATA ?? '', 'npm-cache', '_npx')
      const hits = []
      for (const dir of readdirSync(npxRoot)) {
        const p = join(npxRoot, dir, 'node_modules', 'esbuild')
        try {
          require.resolve(join(p, 'package.json'))
          hits.push(p)
        } catch { /* skip */ }
      }
      if (hits.length === 0) throw new Error('esbuild not found — run: npm i -D esbuild')
      return require(join(hits[0], 'package.json').replace(/package\.json$/, ''))
    }
  }
}

const esbuild = resolveEsbuild()
const { build } = esbuild

mkdirSync(join(root, 'client'), { recursive: true })
mkdirSync(join(root, 'lib'), { recursive: true })

// ---- 1. client bundle (browser) ----
await build({
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
    js: 'window.__ModuleLoader__.load({ id: "dsh-job-radar", factory: (require) => {\nvar module = { exports: {} };\nvar exports = module.exports;',
  },
  footer: {
    js: 'return module.exports; } });',
  },
})

// ---- 2. host plugin: ESM bundle for the cordis loader ----
// cordis and the typert protocol are provided by the DSH host at runtime;
// node builtins are resolved by the node runtime itself.
await build({
  entryPoints: [join(root, 'src', 'index.ts')],
  bundle: true,
  format: 'esm',
  outfile: join(root, 'lib', 'index.js'),
  platform: 'node',
  target: ['node20'],
  tsconfigRaw: '{"compilerOptions":{"useDefineForClassFields":false}}',
  external: ['@deepseek-ai/cordis', '@deepseek-ai/dsh-typert-protocol', 'node:fs', 'node:path'],
  minify: false,
  sourcemap: false,
})

console.log('[dsh-job-radar] build ok: lib/index.js, client/client.js')
