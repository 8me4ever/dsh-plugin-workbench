export interface SyncFile {
  path: string
  status: string
  tracked: boolean
  bytes: number
  blocker?: string
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

export interface CommitPreview {
  paths: readonly string[]
  message: string
  diff: string
  truncated: boolean
  warnings: readonly string[]
  token: string
}

export interface CommitResult {
  commit: string
  status: SyncStatus
}

export interface WorkbenchSyncFace {
  refresh(): Promise<SyncStatus>
  preview(): Promise<SyncStatus>
  commitPreview(paths: readonly string[], message: string): Promise<CommitPreview>
  commit(paths: readonly string[], message: string, previewToken: string): Promise<CommitResult>
}

interface RemoteResult<T> {
  ok?: boolean
  value?: T
  error?: { message?: string }
}

type RawNamespace = Record<string, (...args: unknown[]) => Promise<RemoteResult<unknown>>>

async function unwrap<T>(call: Promise<RemoteResult<unknown>>, method: string): Promise<T> {
  const result = await call
  if (result === null || typeof result !== 'object' || result.ok !== true) {
    throw new Error(result?.error?.message ?? `workbenchSync.${method} 调用失败`)
  }
  return result.value as T
}

export function toWorkbenchSyncFace(raw: unknown): WorkbenchSyncFace | undefined {
  if (raw === null || typeof raw !== 'object') return undefined
  const ns = raw as RawNamespace
  if (typeof ns.refresh !== 'function' || typeof ns.preview !== 'function'
    || typeof ns.commitPreview !== 'function' || typeof ns.commit !== 'function') return undefined
  return {
    refresh: () => unwrap<SyncStatus>(ns.refresh(), 'refresh'),
    preview: () => unwrap<SyncStatus>(ns.preview(), 'preview'),
    commitPreview: (paths, message) => unwrap<CommitPreview>(ns.commitPreview(paths, message), 'commitPreview'),
    commit: (paths, message, previewToken) => unwrap<CommitResult>(ns.commit(paths, message, previewToken), 'commit'),
  }
}
