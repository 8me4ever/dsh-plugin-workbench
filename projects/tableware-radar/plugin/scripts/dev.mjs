/**
 * The whole edit → build → install loop in one command, for dsh-tableware-radar.
 *
 * A `file:` plugin is **packed and copied** into the profile (pnpm honours the package's
 * `files` whitelist), not symlinked. So editing source and rebuilding is not enough — the
 * profile keeps serving the copy from the last install until you add it again.
 *
 * And `add` alone is not reliably enough either: when the dependency spec has not changed,
 * pnpm reports "Already up to date" and **skips the repack**. The script therefore compares
 * the installed copy against the fresh build and forces a remove + add when they differ.
 *
 * Steps: build → install → verify the profile is serving the fresh build. Then restart `dsh web`.
 *
 * Usage:
 *   node scripts/dev.mjs                 # web profile
 *   node scripts/dev.mjs --profile web
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))

const argv = process.argv.slice(2)
const profile = readFlag('--profile') ?? 'web'

/** The build artifacts whose content proves which bundle the profile serves. */
const PROOFS = ['lib/index.js', 'lib/typert.host.js', 'lib/client.js']
const installedRoot = join(homedir(), '.dsh', 'profiles', profile, 'node_modules', pkg.name)

/** Read `--name value`. */
function readFlag(name) {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}

/**
 * Locate the dsh entry point.
 *
 * We call the JS entry with this same node binary instead of spawning the `dsh` shell shim:
 * that avoids Windows `.cmd` quoting entirely, and pins the CLI to the node version this
 * plugin was built against.
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

process.stdout.write('\n▸ build\n')
execFileSync(process.execPath, [join(root, 'build.mjs')], { stdio: 'inherit', cwd: root })

const spec = `file:${root.replace(/\\/g, '/')}`
process.stdout.write(`\n▸ install into profile "${profile}"\n  ${pkg.name} ← ${spec}\n`)
let status = dsh(['add', spec])

if (status === 0 && !copyIsCurrent()) {
  process.stdout.write('\n▸ the profile is still serving the previous copy; forcing a reinstall…\n')
  status = dsh(['remove', pkg.name])
  if (status === 0) status = dsh(['add', spec])
}

if (status !== 0) {
  process.stdout.write(`\ninstall failed (exit ${status}).\n`)
  process.exit(status)
}

if (!copyIsCurrent()) {
  process.stdout.write(
    `\n⚠ could not confirm the install: ${PROOFS.join(' / ')} under\n  ${installedRoot}\n`
    + '  do not match the fresh build. Recover by hand:\n'
    + `  dsh plugin --profile ${profile} remove ${pkg.name}\n`
    + `  dsh plugin --profile ${profile} add "${spec}"\n`,
  )
  process.exit(1)
}

process.stdout.write(`\n✓ the profile is serving the current build (${PROOFS.join(' + ')} match).\n`)
process.stdout.write('\ndone. now restart the host and reload the page:\n' + `  dsh web --profile ${profile}\n`)
