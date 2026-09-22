/** Unified DSH host: one installed package owns both project data faces. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { existsSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve, sep } from 'node:path'
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

interface SyncFile { path: string; status: string; tracked: boolean; bytes: number; blocker?: string }
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

interface CommitPreview {
  paths: string[]
  message: string
  diff: string
  truncated: boolean
  warnings: string[]
  token: string
}

interface CommitResult { commit: string; status: SyncStatus }

const MAX_COMMIT_FILE_BYTES = 5 * 1024 * 1024
const MAX_DIFF_CHARS = 160_000
const SENSITIVE_PATH = /(?:^|\/)(?:\.env(?:\.|$)|\.npmrc$|credentials?(?:\.|$)|secrets?(?:\.|$)|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|$)|[^/]+\.(?:pem|key|p12|pfx))|(?:^|\/)[^/]*(?:token|secret)[^/]*$/i

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

  private safePath(path: string): string {
    if (!path || path.includes('\0')) throw new Error('文件路径无效')
    const absolute = resolve(this.workspace, path)
    const root = resolve(this.workspace)
    if (absolute !== root && !absolute.startsWith(`${root}${sep}`)) throw new Error(`文件不在工作台仓库中：${path}`)
    return absolute
  }

  private fileInfo(path: string, tracked: boolean): Pick<SyncFile, 'bytes' | 'blocker'> {
    const normalized = path.replace(/\\/g, '/')
    if (normalized.includes(' -> ')) return { bytes: 0, blocker: '重命名文件暂不支持在工作台内提交，请使用 Git 命令处理' }
    if (SENSITIVE_PATH.test(normalized)) return { bytes: 0, blocker: '疑似包含密钥、凭据或 Token，不允许从工作台提交' }
    try {
      const stat = statSync(this.safePath(path))
      if (!stat.isFile()) return { bytes: stat.size, blocker: '不是普通文件，不能从工作台提交' }
      if (stat.size > MAX_COMMIT_FILE_BYTES) return { bytes: stat.size, blocker: `文件超过 ${MAX_COMMIT_FILE_BYTES / 1024 / 1024} MB 限制` }
      return { bytes: stat.size }
    } catch {
      return tracked ? { bytes: 0 } : { bytes: 0, blocker: '文件不存在或无法读取' }
    }
  }

  private status(fetchedAt: string): SyncStatus {
    const branch = this.git(['branch', '--show-current'])
    const counts = this.git(['rev-list', '--left-right', '--count', 'HEAD...origin/main']).split(/\s+/)
    const raw = this.git(['status', '--porcelain=v1', '-z', '--untracked-files=all'])
    const entries = raw ? raw.split('\0').filter(Boolean) : []
    const files: SyncFile[] = []
    for (let index = 0; index < entries.length; index += 1) {
      const line = entries[index]
      const tracked = !line.startsWith('??')
      const path = line.slice(3)
      const status = line.slice(0, 2)
      const info = this.fileInfo(path, tracked)
      if (/[RC]/.test(status)) {
        index += 1 // porcelain -z emits the original path as the next field
        info.blocker = '重命名或复制文件暂不支持在工作台内提交，请使用 Git 命令处理'
      }
      files.push({ status, path, tracked, ...info })
    }
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

  private validateMessage(message: string): string {
    const clean = message.trim()
    if (!clean) throw new Error('提交说明不能为空')
    if (clean.length > 200) throw new Error('提交说明不能超过 200 个字符')
    return clean
  }

  private selectedFiles(paths: string[]): SyncFile[] {
    const unique = [...new Set(paths)]
    if (unique.length === 0) throw new Error('请至少选择一个文件')
    const current = this.status(new Date().toISOString())
    if (current.blockers.length) throw new Error(current.blockers.join('\n'))
    const byPath = new Map(current.files.map((file) => [file.path, file]))
    return unique.map((path) => {
      this.safePath(path)
      const file = byPath.get(path)
      if (!file) throw new Error(`文件已变化或不再存在于待提交列表：${path}`)
      if (file.blocker) throw new Error(`${path}：${file.blocker}`)
      return file
    })
  }

  private fileDiff(file: SyncFile): string {
    if (file.tracked) return this.git(['diff', '--no-ext-diff', '--no-color', 'HEAD', '--', file.path])
    const content = readFileSync(this.safePath(file.path))
    if (content.includes(0)) return `diff --git a/${file.path} b/${file.path}\nnew file mode 100644\nBinary file ${file.path} added`
    const body = content.toString('utf8').split(/\r?\n/).map((line) => `+${line}`).join('\n')
    return `diff --git a/${file.path} b/${file.path}\nnew file mode 100644\n--- /dev/null\n+++ b/${file.path}\n@@ -0,0 +1 @@\n${body}`
  }

  private makePreview(paths: string[], message: string): CommitPreview {
    const cleanMessage = this.validateMessage(message)
    const files = this.selectedFiles(paths)
    const fullDiff = files.map((file) => this.fileDiff(file)).filter(Boolean).join('\n\n')
    const truncated = fullDiff.length > MAX_DIFF_CHARS
    const diff = truncated ? `${fullDiff.slice(0, MAX_DIFF_CHARS)}\n\n… diff 已截断 …` : fullDiff
    const warnings = files
      .filter((file) => file.status[0] !== ' ' && file.status[0] !== '?')
      .map((file) => `${file.path} 已有暂存内容；本次将提交该文件当前的完整改动`)
    const fingerprint = JSON.stringify({ paths: files.map((file) => file.path), message: cleanMessage, diff: fullDiff })
    return {
      paths: files.map((file) => file.path), message: cleanMessage, diff, truncated, warnings,
      token: createHash('sha256').update(fingerprint).digest('hex'),
    }
  }

  @Remote
  commitPreview(paths: string[], message: string): CommitPreview {
    return this.makePreview(paths, message)
  }

  @Remote
  commit(paths: string[], message: string, previewToken: string): CommitResult {
    const preview = this.makePreview(paths, message)
    if (preview.token !== previewToken) throw new Error('文件在预览后发生了变化，请重新生成提交预览')

    const indexPathRaw = this.git(['rev-parse', '--git-path', 'index'])
    const indexPath = isAbsolute(indexPathRaw) ? indexPathRaw : resolve(this.workspace, indexPathRaw)
    const oldIndex = existsSync(indexPath) ? readFileSync(indexPath) : null
    try {
      this.git(['add', '-A', '--', ...preview.paths])
      this.git(['commit', '--only', '-m', preview.message, '--', ...preview.paths])
    } catch (reason) {
      if (oldIndex === null) rmSync(indexPath, { force: true })
      else writeFileSync(indexPath, oldIndex)
      throw reason
    }
    return { commit: this.git(['rev-parse', '--short', 'HEAD']), status: this.status(new Date().toISOString()) }
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
