/**
 * dsh-job-radar host plugin: mounts the `jobRadar` remote that reads the
 * local job-radar jobs.json snapshot (list/stats/status), so the DSH web
 * client can browse and filter the same job data the local FastAPI
 * dashboard uses — no separate server needed.
 *
 * The service is exposed through the typert remote protocol (same pattern
 * as dsh-at-file): the client resolves it via `reflect.get('remote.jobRadar')`.
 */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

/** Cordis plugin name (the Loader entry and client bundle id). */
export const name = 'dsh-job-radar'

/** No required services. */
export const inject: string[] = []

/** Host plugin configuration. */
export interface Config {
  /** Absolute path to job-radar data dir (containing jobs.json). */
  dataDir: string
}

const ALL_STATUS = ['new', 'applied', 'interested', 'rejected']

/**
 * Remote service registered under the `jobRadar` wire namespace.
 * Methods decorated with @Remote are callable from the web client.
 */
export class JobRadarRuntime extends TypertRemoteService {
  private readonly snapshotPath: string
  private readonly log: Context['logger']

  constructor(ctx: Context, dataDir: string) {
    super(ctx, 'jobRadar')
    this.snapshotPath = join(dataDir, 'jobs.json')
    this.log = ctx.logger
  }

  private readSnapshot(): { jobs: any[] } {
    try {
      if (!existsSync(this.snapshotPath)) return { jobs: [] }
      const data = JSON.parse(readFileSync(this.snapshotPath, 'utf-8'))
      return { jobs: Array.isArray(data.jobs) ? data.jobs : [] }
    } catch (err) {
      this.log.warn(`[dsh-job-radar] read jobs.json failed: ${(err as Error).message}`)
      return { jobs: [] }
    }
  }

  private writeSnapshot(jobs: any[]): void {
    try {
      writeFileSync(
        this.snapshotPath,
        JSON.stringify({ version: 1, exported_at: new Date().toISOString(), jobs }, null, 2),
        'utf-8',
      )
    } catch (err) {
      this.log.warn(`[dsh-job-radar] write jobs.json failed: ${(err as Error).message}`)
    }
  }

  @Remote
  ping(): { ok: true } {
    return { ok: true }
  }

  @Remote
  list(filter?: { grade?: string; status?: string; days?: number }): { jobs: any[]; total: number } {
    const { jobs } = this.readSnapshot()
    const f = filter ?? {}
    let out = jobs
    if (f.grade) out = out.filter((j) => j.grade === f.grade)
    if (f.status) out = out.filter((j) => j.status === f.status)
    if (f.days) {
      const cutoff = Date.now() - f.days * 86400_000
      out = out.filter((j) => {
        const t = j.created_at ? Date.parse(j.created_at) : 0
        return !Number.isNaN(t) && t >= cutoff
      })
    }
    out = [...out].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    return { jobs: out, total: out.length }
  }

  @Remote
  stats(): Record<string, number> {
    const { jobs } = this.readSnapshot()
    const s: Record<string, number> = { total: jobs.length }
    for (const j of jobs) {
      s[`grade_${j.grade}`] = (s[`grade_${j.grade}`] ?? 0) + 1
      s[`status_${j.status}`] = (s[`status_${j.status}`] ?? 0) + 1
    }
    return s
  }

  @Remote
  setStatus(jid: string, status: string): { ok: boolean; error?: string } {
    if (!ALL_STATUS.includes(status)) return { ok: false, error: `invalid status: ${status}` }
    const { jobs } = this.readSnapshot()
    const idx = jobs.findIndex((j) => j.id === jid)
    if (idx < 0) return { ok: false, error: `job not found: ${jid}` }
    jobs[idx] = { ...jobs[idx], status, updated_at: new Date().toISOString() }
    this.writeSnapshot(jobs)
    return { ok: true }
  }
}

/**
 * Mount the jobRadar remote.
 * @param ctx - host cordis context.
 * @param config - plugin configuration (from the profile patch).
 */
export function apply(ctx: Context, config?: Partial<Config>): void {
  const dataDir = config?.dataDir ?? ''
  if (!dataDir) {
    ctx.logger.warn('[dsh-job-radar] dataDir not configured — dashboard disabled. Set it in the profile patch: config.dataDir')
    return
  }
  new JobRadarRuntime(ctx, dataDir)
  ctx.logger.info(`[dsh-job-radar] mounted, dataDir=${dataDir}`)
}
