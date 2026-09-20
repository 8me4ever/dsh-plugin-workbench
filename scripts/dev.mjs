/**
 * The whole edit → build → install loop in one command.
 *
 * Why a script at all: a `file:` plugin is **packed and copied** into the
 * profile (pnpm honours the package's `files` whitelist), not symlinked. So
 * editing source and rebuilding is not enough — the profile keeps serving the
 * copy from the last install until you add it again.
 *
 * And `add` on its own is not reliably enough either: when the dependency spec
 * has not changed, pnpm reports "Already up to date" and **skips the repack**,
 * leaving the previous bundle in place. The script therefore compares the
 * installed copy against the fresh build and forces a remove + add when they
 * differ. Without that check the loop fails silently, which is the single most
 * confusing way to lose ten minutes.
 *
 * Steps: build → smoke test → install → verify the profile is serving the
 * fresh build. Then restart `dsh web`.
 *
 * Usage:
 *   node scripts/dev.mjs                 # web profile
 *   node scripts/dev.mjs --profile other
 *   node scripts/dev.mjs --skip-smoke
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))

const argv = process.argv.slice(2)
const profile = readFlag('--profile') ?? 'web'
const skipSmoke = argv.includes('--skip-smoke')

/** The build artifacts whose content proves which bundle the profile serves. */
const PROOFS = ['client/client.js', 'lib/index.js']
const installedRoot = join(homedir(), '.dsh', 'profiles', profile, 'node_modules', pkg.name)
const locationFile = join(homedir(), '.dsh', 'dsh-plugin-workbench.json')

/** Read `--name value`. */
function readFlag(name) {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}

/** Run a node script in the project root, inheriting stdio. */
function run(label, script, args = []) {
  process.stdout.write(`\n▸ ${label}\n`)
  execFileSync(process.execPath, [script, ...args], { stdio: 'inherit', cwd: root })
}

/**
 * Locate the dsh entry point.
 *
 * We call the JS entry with this same node binary instead of spawning the
 * `dsh` shell shim: that avoids Windows `.cmd` quoting entirely, and pins the
 * CLI to the node version this plugin was built against.
 */
function findDshEntry() {
  const candidates = []
  try {
    const globalRoot = execFileSync('npm', ['root', '-g'], { encoding: 'utf-8' }).trim()
    candidates.push(join(globalRoot, '@deepseek-ai', 'dsh', 'lib', 'bin.js'))
  } catch { /* npm not on PATH */ }
  if (process.env.APPDATA) {
    candidates.push(join(process.env.APPDATA, 'npm', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js'))
  }
  const found = candidates.find((candidate) => existsSync(candidate))
  if (!found) {
    throw new Error(
      'dsh not found. Install it first (npm i -g @deepseek-ai/dsh), or install manually:\n'
      + `  dsh plugin --profile ${profile} add "file:${root.replace(/\\/g, '/')}"`,
    )
  }
  return found
}

/** Run the dsh CLI in the profile, inheriting stdio. Returns the exit status. */
function dsh(args) {
  const result = spawnSync(process.execPath, [findDshEntry(), 'plugin', '--profile', profile, ...args], {
    stdio: 'inherit',
    cwd: root,
  })
  return result.status ?? 1
}

/** True when the profile is serving byte-for-byte what the build just produced. */
function copyIsCurrent() {
  try {
    return PROOFS.every((proof) => (
      readFileSync(join(installedRoot, proof), 'utf8') === readFileSync(join(root, proof), 'utf8')
    ))
  } catch {
    return false
  }
}

run('build', join(root, 'build.mjs'))

// The profile receives a packed copy, while Git operations and mutable snapshots
// must target the real checkout. Keep that machine-local pointer outside Git.
mkdirSync(dirname(locationFile), { recursive: true })
writeFileSync(locationFile, `${JSON.stringify({ workspaceDir: root }, null, 2)}\n`, 'utf8')
process.stdout.write(`\n▸ registered unified workspace\n  ${locationFile} → ${root}\n`)

if (skipSmoke) {
  process.stdout.write('\n▸ smoke test skipped (--skip-smoke)\n')
} else {
  run('smoke test', join(root, 'scripts', 'smoke-client.mjs'))
}

const spec = `file:${root.replace(/\\/g, '/')}`
process.stdout.write(`\n▸ install into profile "${profile}"\n  ${pkg.name} ← ${spec}\n`)
let status = dsh(['add', spec])

if (status === 0 && !copyIsCurrent()) {
  process.stdout.write(
    '\n▸ the profile is still serving the previous copy.\n'
    + '  pnpm treats an unchanged `file:` spec as "already up to date" and skips\n'
    + '  the repack, so re-adding alone does not refresh it. Forcing a reinstall…\n',
  )
  status = dsh(['remove', pkg.name])
  if (status === 0) status = dsh(['add', spec])
}

if (status !== 0) {
  process.stdout.write(`\ninstall failed (exit ${status}). The build output is still in lib/ and client/.\n`)
  process.exit(status)
}

if (!copyIsCurrent()) {
  process.stdout.write(
    `\n⚠ could not confirm the install: ${PROOFS.join(' / ')} under\n`
    + `  ${installedRoot}\n`
    + '  do not match the fresh build. The page would serve a stale bundle.\n'
    + `  Recover by hand:\n  dsh plugin --profile ${profile} remove ${pkg.name}\n`
    + `  dsh plugin --profile ${profile} add "${spec}"\n`,
  )
  process.exit(1)
}

process.stdout.write(`\n✓ the profile is serving the current build (${PROOFS.join(' + ')} match).\n`)
process.stdout.write(
  '\ndone. now restart the host and reload the page:\n'
  + `  dsh web --profile ${profile}\n`
  + 'then reload the browser tab and look at the entry at the sidebar foot.\n',
)
