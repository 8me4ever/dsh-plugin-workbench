export interface SyncFile {
  path: string
  status: string
  tracked: boolean
}

export interface SyncStatus {
  branch: string
  isMain: boolean
  ahead: number
  behind: number
  files: readonly SyncFile[]
  localCommits: readonly string[]
  remoteCommits: readonly string[]
  blockers: readonly string[]
  fetchedAt: string
}

export interface WorkbenchSyncFace {
  refresh(): Promise<SyncStatus>
  preview(): Promise<SyncStatus>
}

interface RemoteResult<T> {
  ok?: boolean
  value?: T
  error?: { message?: string }
}

type RawNamespace = Record<string, (...args: unknown[]) => Promise<RemoteResult<unknown>>>

async function unwrap(call: Promise<RemoteResult<unknown>>, method: string): Promise<SyncStatus> {
  const result = await call
  if (result === null || typeof result !== 'object' || result.ok !== true) {
    throw new Error(result?.error?.message ?? `workbenchSync.${method} 调用失败`)
  }
  return result.value as SyncStatus
}

export function toWorkbenchSyncFace(raw: unknown): WorkbenchSyncFace | undefined {
  if (raw === null || typeof raw !== 'object') return undefined
  const ns = raw as RawNamespace
  if (typeof ns.refresh !== 'function' || typeof ns.preview !== 'function') return undefined
  return {
    refresh: () => unwrap(ns.refresh(), 'refresh'),
    preview: () => unwrap(ns.preview(), 'preview'),
  }
}
