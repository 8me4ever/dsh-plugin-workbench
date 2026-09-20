import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const bundle = readFileSync(join(root, 'lib', 'index.js'), 'utf8')

for (const symbol of ['JobRadarRuntime', 'TablewareRadarRuntime', 'WorkbenchSyncRuntime', 'jobRadar', 'tablewareRadar', 'workbenchSync']) {
  assert.ok(bundle.includes(symbol), `host bundle is missing ${symbol}`)
}

const jobsPath = join(root, 'projects', 'job-hunting', 'code', 'job-radar', 'data', 'jobs.json')
assert.ok(existsSync(jobsPath), 'tracked Job Radar snapshot is missing')
const jobs = JSON.parse(readFileSync(jobsPath, 'utf8'))
assert.ok(Array.isArray(jobs.jobs), 'jobs.json must contain a jobs array')

const examplePath = join(root, 'projects', 'tableware-radar', 'data', 'analysis.example.json')
assert.ok(existsSync(examplePath), 'Tableware analysis example is missing')
const analysis = JSON.parse(readFileSync(examplePath, 'utf8'))
for (const key of ['generated_at', 'dimensions', 'by_asin', 'opportunities', 'data_quality']) {
  assert.ok(key in analysis, `analysis example is missing ${key}`)
}

console.log(`[dsh-plugin-workbench] host smoke ok: ${jobs.jobs.length} jobs + all unified remotes`)
