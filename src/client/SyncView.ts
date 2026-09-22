import { createElement as h, useEffect, useState, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import { notice, sectionHeader } from './parts.ts'
import { CODE, HINT, OUTLINE_BUTTON, T } from './tokens.ts'
import type { CommitPreview, SyncStatus, WorkbenchSyncFace } from './workbenchSyncRemote.ts'

export function createSyncView(resolve: () => WorkbenchSyncFace | undefined, t: Translate) {
  return function SyncView(): ReactElement {
    const [status, setStatus] = useState<SyncStatus | null>(null)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const [selected, setSelected] = useState<string[]>([])
    const [message, setMessage] = useState('')
    const [commitPreview, setCommitPreview] = useState<CommitPreview | null>(null)
    const [committed, setCommitted] = useState('')

    const load = async (fetchRemote: boolean): Promise<void> => {
      const remote = resolve()
      if (remote === undefined) {
        setError(t('sync.unavailable'))
        return
      }
      setLoading(true)
      setError('')
      setCommitted('')
      try {
        setStatus(await (fetchRemote ? remote.refresh() : remote.preview()))
        setCommitPreview(null)
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason))
      } finally {
        setLoading(false)
      }
    }

    useEffect(() => { void load(true) }, [])

    const toggle = (path: string): void => {
      setSelected((current) => current.includes(path) ? current.filter((item) => item !== path) : [...current, path])
      setCommitPreview(null)
      setCommitted('')
    }

    const prepare = async (): Promise<void> => {
      const remote = resolve()
      if (remote === undefined) { setError(t('sync.unavailable')); return }
      setLoading(true)
      setError('')
      setCommitted('')
      try { setCommitPreview(await remote.commitPreview(selected, message)) }
      catch (reason) { setCommitPreview(null); setError(reason instanceof Error ? reason.message : String(reason)) }
      finally { setLoading(false) }
    }

    const commit = async (): Promise<void> => {
      const remote = resolve()
      if (remote === undefined || commitPreview === null) return
      setLoading(true)
      setError('')
      try {
        const result = await remote.commit(commitPreview.paths, commitPreview.message, commitPreview.token)
        setStatus(result.status)
        setSelected([])
        setMessage('')
        setCommitPreview(null)
        setCommitted(`${t('sync.committed')} ${result.commit}`)
      } catch (reason) {
        setCommitPreview(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      } finally { setLoading(false) }
    }

    return h('div', { 'data-sync-view': '', style: { display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 880 } },
      h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: 12 } },
        h('div', { style: { flex: '1 1 auto' } },
          h('h2', { style: { margin: 0, fontSize: 18, fontWeight: 600 } }, t('sync')),
          h('div', { style: HINT }, t('sync.subtitle')),
        ),
        h('button', { type: 'button', disabled: loading, onClick: () => { void load(true) }, style: OUTLINE_BUTTON }, loading ? t('loading') : t('sync.refresh')),
      ),
      error ? notice(error, T.danger) : null,
      committed ? notice(committed, T.ok) : null,
      status === null && !error ? notice(t('loading'), T.text3) : null,
      status === null ? null : summary(status, t),
      status === null ? null : commitSection(status, selected, message, commitPreview, loading, toggle, (value) => {
        setMessage(value); setCommitPreview(null); setCommitted('')
      }, prepare, commit, t),
      status === null ? null : listSection(t('sync.localCommits'), status.localCommits, t('sync.none')),
      status === null ? null : listSection(t('sync.remoteCommits'), status.remoteCommits, t('sync.none')),
    )
  }
}

function commitSection(
  status: SyncStatus,
  selected: readonly string[],
  message: string,
  preview: CommitPreview | null,
  loading: boolean,
  toggle: (path: string) => void,
  setMessage: (message: string) => void,
  prepare: () => Promise<void>,
  commit: () => Promise<void>,
  t: Translate,
): ReactElement {
  const canPrepare = !loading && selected.length > 0 && message.trim().length > 0 && status.blockers.length === 0
  return h('section', { 'data-sync-commit-section': '', style: { display: 'flex', flexDirection: 'column', gap: 10 } },
    sectionHeader(t('sync.localChanges')),
    status.files.length === 0 ? notice(t('sync.clean'), T.text3) : h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
      ...status.files.map((file) => h('label', {
        key: file.path, 'data-sync-file': file.path,
        style: { display: 'flex', gap: 9, alignItems: 'flex-start', padding: '8px 10px', border: `1px solid ${file.blocker ? T.danger : T.border1}`, borderRadius: 7, background: T.bgLayer2 },
      },
      h('input', { type: 'checkbox', checked: selected.includes(file.path), disabled: Boolean(file.blocker) || loading, onChange: () => toggle(file.path), style: { marginTop: 2 } }),
      h('span', { style: { flex: '1 1 auto', minWidth: 0 } },
        h('span', { style: CODE }, `${file.status}  ${file.path}`),
        h('span', { style: { ...HINT, display: 'block', color: file.blocker ? T.danger : T.text3 } }, file.blocker ?? `${formatBytes(file.bytes)} · ${file.tracked ? t('sync.tracked') : t('sync.untracked')}`),
      ))),
    ),
    status.files.length === 0 ? null : h('textarea', {
      value: message, disabled: loading, maxLength: 200, placeholder: t('sync.messagePlaceholder'),
      onChange: (event: { target: { value: string } }) => setMessage(event.target.value),
      style: { minHeight: 64, resize: 'vertical', border: `1px solid ${T.border2}`, borderRadius: 7, background: T.bgLayer1, color: T.text1, font: 'inherit', fontSize: 13, padding: '9px 10px' },
    }),
    status.files.length === 0 ? null : h('div', { style: { display: 'flex', gap: 8, alignItems: 'center' } },
      h('button', { type: 'button', 'data-sync-preview': '', disabled: !canPrepare, onClick: () => { void prepare() }, style: OUTLINE_BUTTON }, t('sync.prepare')),
      h('span', { style: HINT }, t('sync.localOnly')),
    ),
    preview === null ? null : h('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
      notice(t('sync.confirmHint'), T.warn),
      ...preview.warnings.map((warning) => notice(warning, T.warn)),
      h('div', { style: { ...CODE, maxHeight: 360, overflow: 'auto', whiteSpace: 'pre', padding: 10, border: `1px solid ${T.border1}`, borderRadius: 7, background: T.bgLayer2 } }, preview.diff || t('sync.noDiff')),
      h('button', { type: 'button', 'data-sync-commit': '', disabled: loading, onClick: () => { void commit() }, style: { ...OUTLINE_BUTTON, alignSelf: 'flex-start', borderColor: T.warn } }, t('sync.confirmCommit')),
    ),
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function summary(status: SyncStatus, t: Translate): ReactElement {
  const cells: [string, string, string][] = [
    [t('sync.branch'), status.branch || '(detached)', status.isMain ? T.ok : T.danger],
    [t('sync.ahead'), String(status.ahead), status.ahead ? T.warn : T.text1],
    [t('sync.behind'), String(status.behind), status.behind ? T.info : T.text1],
    [t('sync.changes'), String(status.files.length), status.files.length ? T.warn : T.text1],
  ]
  return h('section', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
    h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 } },
      ...cells.map(([label, value, color]) => h('div', { key: label, style: { border: `1px solid ${T.border1}`, borderRadius: 8, padding: '10px 12px', background: T.bgLayer2 } },
        h('div', { style: HINT }, label), h('div', { style: { color, fontSize: 18, fontWeight: 600 } }, value),
      )),
    ),
    status.blockers.length ? notice(status.blockers.join('\n'), T.danger) : notice(t('sync.ready'), T.ok),
    h('div', { style: HINT }, `${t('sync.fetchedAt')} ${new Date(status.fetchedAt).toLocaleString()}`),
  )
}

function listSection(title: string, rows: readonly string[], empty: string): ReactElement {
  return h('section', null,
    sectionHeader(title),
    rows.length === 0 ? notice(empty, T.text3) : h('div', { style: { ...CODE, paddingTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-all' } }, rows.join('\n')),
  )
}
