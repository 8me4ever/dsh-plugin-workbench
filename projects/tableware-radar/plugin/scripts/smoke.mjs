/**
 * Structural smoke test for the built plugin artifacts (no host required).
 *
 * Verifies: the host TYPERT manifest shape (0-parameter methods, strict codecs),
 * the host service contract (getStatus/getAnalysis), and the client bundle envelope.
 *
 * Run: node scripts/smoke.mjs
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const url = (rel) => pathToFileURL(join(root, rel)).href

// ---- host TYPERT manifest ----
const { TYPERT } = await import(url('lib/typert.host.js'))
assert.equal(TYPERT.package, 'dsh-tableware-radar')
assert.equal(TYPERT.face, 'host')
assert.equal(TYPERT.invocations.length, 2)
assert.deepEqual(
  TYPERT.invocations.map((i) => i.method).sort(),
  ['getAnalysis', 'getStatus'],
)
for (const inv of TYPERT.invocations) {
  assert.equal(inv.service, 'tablewareRadar')
  assert.equal(inv.namespace, 'tablewareRadar')
  assert.equal(inv.parameters.length, 0, `${inv.method} must take 0 parameters`)
  assert.equal(inv.result.mode, 'strict', `${inv.method} result must be a strict codec`)
  assert.ok(inv.result.schema, `${inv.method} result must carry a schema`)
}

// ---- host service ----
const host = await import(url('lib/index.js'))
assert.equal(host.name, 'dsh-tableware-radar')
const service = new host.TablewareRadarService('F:/Samuel/dsh-plugins/dsh-tableware-radar/data')
const status = service.getStatus()
assert.equal(typeof status.present, 'boolean')
assert.ok('path' in status && 'mtimeMs' in status && 'bytes' in status && 'generatedAt' in status)
assert.equal(typeof service.getAnalysis(), 'object') // object or null

// ---- client bundle envelope ----
const client = readFileSync(join(root, 'lib', 'client.js'), 'utf8')
assert.ok(
  client.startsWith('window.__ModuleLoader__.load({ id: "dsh-tableware-radar"'),
  'client bundle must be wrapped in the module-loader envelope',
)

console.log('[smoke] dsh-tableware-radar artifacts ok')
console.log('  methods :', TYPERT.invocations.map((i) => i.method).join(', '))
console.log('  status  :', JSON.stringify(status))
