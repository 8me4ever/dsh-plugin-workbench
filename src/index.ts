/** Unified DSH host: one installed package owns both project data faces. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { existsSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve } from 'node:path'
import { execFileSync } from 'node:child_process'

export const name = 'dsh-plugin-workbench'
export const inject: string[] = []

export interface Config {
  workspaceDir?: string
  jobDataDir?: string
  tablewareDataDir?: string
}

const STATUS = new Set(['new', 'applied', 'interested', 'rejected'])
const LOCATION_FILE = join(homedir(), '.dsh', 'dsh-plugin-workbench.json')

function readJson(path: string): any | undefined {
  try { return JSON.parse(readFileSync(path, 'utf8')) } catch { return undefined }
}

function resolveWorkspace(config?: Config): string {
  if (config?.workspaceDir) return resolve(config.workspaceDir)
  if (process.env.DSH_WORKBENCH_ROOT) return resolve(process.env.DSH_WORKBENCH_ROOT)
  const registered = readJson(LOCATION_FILE)?.workspaceDir
  if (typeof registered === 'string' && registered) return resolve(registered)
  return process.cwd()
}

function resolveDataDir(workspace: string, override: string | undefined, fallback: string): string {
  if (!override) return join(workspace, fallback)
  return isAbsolute(override) ? override : resolve(workspace, override)
}

function atomicJsonWrite(path: string, value: unknown): void {
  const temporary = `${path}.tmp`
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
  renameSync(temporary, path)
}

export class JobRadarRuntime extends TypertRemoteService {
  private readonly snapshotPath: string

  constructor(ctx: Context, dataDir: string) {
    super(ctx, 'jobRadar')
    this.snapshotPath = join(dataDir, 'jobs.json')
  }

  private snapshot(): { version?: number; exported_at?: string; jobs: any[] } {
    const data = readJson(this.snapshotPath)
    return { version: data?.version, exported_at: data?.exported_at, jobs: Array.isArray(data?.jobs) ? data.jobs : [] }
  }

  @Remote ping(): { ok: true } { return { ok: true } }

  @Remote
  list(filter?: { grade?: string; status?: string; days?: number }): { jobs: any[]; total: number } {
    const f = filter ?? {}
    let jobs = this.snapshot().jobs
    if (f.grade) jobs = jobs.filter((job) => job.grade === f.grade)
    if (f.status) jobs = jobs.filter((job) => job.status === f.status)
    if (f.days) {
      const cutoff = Date.now() - f.days * 86_400_000
      jobs = jobs.filter((job) => {
        const created = Date.parse(job.created_at ?? '')
        return !Number.isNaN(created) && created >= cutoff
      })
    }
    jobs = [...jobs].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    return { jobs, total: jobs.length }
  }

  @Remote
  stats(): Record<string, number> {
    const jobs = this.snapshot().jobs
    const stats: Record<string, number> = { total: jobs.length }
    for (const job of jobs) {
      stats[`grade_${job.grade}`] = (stats[`grade_${job.grade}`] ?? 0) + 1
      stats[`status_${job.status}`] = (stats[`status_${job.status}`] ?? 0) + 1
    }
    return stats
  }

  @Remote
  setStatus(jobId: string, status: string): { ok: boolean; error?: string } {
    if (!STATUS.has(status)) return { ok: false, error: `invalid status: ${status}` }
    const snapshot = this.snapshot()
    const index = snapshot.jobs.findIndex((job) => job.id === jobId)
    if (index < 0) return { ok: false, error: `job not found: ${jobId}` }
    snapshot.jobs[index] = { ...snapshot.jobs[index], status, updated_at: new Date().toISOString() }
    atomicJsonWrite(this.snapshotPath, {
      version: snapshot.version ?? 1,
      exported_at: new Date().toISOString(),
      jobs: snapshot.jobs,
    })
    return { ok: true }
  }
}

export class TablewareRadarRuntime extends TypertRemoteService {
  private readonly analysisPath: string

  constructor(ctx: Context, dataDir: string) {
    super(ctx, 'tablewareRadar')
    this.analysisPath = join(dataDir, 'analysis.json')
  }

  @Remote getAnalysis(): Record<string, unknown> | null { return readJson(this.analysisPath) ?? null }

  @Remote
  getStatus(): { present: boolean; path: string; mtimeMs: number; bytes: number; generatedAt: string | null } {
    try {
      const stat = statSync(this.analysisPath)
      const analysis = readJson(this.analysisPath)
      return {
        present: true,
        path: this.analysisPath,
        mtimeMs: stat.mtimeMs,
        bytes: stat.size,
        generatedAt: typeof analysis?.generated_at === 'string' ? analysis.generated_at : null,
      }
    } catch {
      return { present: false, path: this.analysisPath, mtimeMs: 0, bytes: 0, generatedAt: null }
    }
  }
}

interface SyncFile { path: string; status: string; tracked: boolean }
interface SyncStatus {
  branch: string
  isMain: boolean
  ahead: number
  behind: number
  files: SyncFile[]
  localCommits: string[]
  remoteCommits: string[]
  blockers: string[]
  fetchedAt: string
}

export class WorkbenchSyncRuntime extends TypertRemoteService {
  constructor(ctx: Context, private readonly workspace: string) {
    super(ctx, 'workbenchSync')
  }

  private git(args: string[]): string {
    return execFileSync('git', args, {
      cwd: this.workspace,
      encoding: 'utf8',
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trimEnd()
  }

  private status(fetchedAt: string): SyncStatus {
    const branch = this.git(['branch', '--show-current'])
    const counts = this.git(['rev-list', '--left-right', '--count', 'HEAD...origin/main']).split(/\s+/)
    const raw = this.git(['status', '--porcelain=v1', '--untracked-files=all'])
    const files = raw ? raw.split(/\r?\n/).filter(Boolean).map((line) => ({
      status: line.slice(0, 2),
      path: line.slice(3),
      tracked: !line.startsWith('??'),
    })) : []
    const localCommits = this.git(['log', '--format=%h %s', 'origin/main..HEAD']).split('\n').filter(Boolean)
    const remoteCommits = this.git(['log', '--format=%h %s', 'HEAD..origin/main']).split('\n').filter(Boolean)
    const blockers: string[] = []
    if (branch !== 'main') blockers.push(`当前分支是 ${branch || '(detached)'}，同步只支持 main`)
    if (files.some((file) => /(?:U|AA|DD)/.test(file.status))) blockers.push('工作区存在尚未解决的 Git 冲突')
    return {
      branch,
      isMain: branch === 'main',
      ahead: Number(counts[0] ?? 0),
      behind: Number(counts[1] ?? 0),
      files,
      localCommits,
      remoteCommits,
      blockers,
      fetchedAt,
    }
  }

  @Remote
  refresh(): SyncStatus {
    this.git(['fetch', '--prune', 'origin', 'main'])
    return this.status(new Date().toISOString())
  }

  @Remote
  preview(): SyncStatus {
    return this.status(new Date().toISOString())
  }
}

export function apply(ctx: Context, config?: Config): void {
  const workspace = resolveWorkspace(config)
  const jobDataDir = resolveDataDir(workspace, config?.jobDataDir, 'projects/job-hunting/code/job-radar/data')
  const tablewareDataDir = resolveDataDir(workspace, config?.tablewareDataDir, 'projects/tableware-radar/data')
  new JobRadarRuntime(ctx, jobDataDir)
  new TablewareRadarRuntime(ctx, tablewareDataDir)
  new WorkbenchSyncRuntime(ctx, workspace)
  ctx.logger.info(`[dsh-plugin-workbench] unified host mounted; workspace=${workspace}`)
  if (!existsSync(workspace)) ctx.logger.warn(`[dsh-plugin-workbench] workspace does not exist: ${workspace}`)
}
