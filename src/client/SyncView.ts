import { createElement as h, useEffect, useState, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import { notice, sectionHeader } from './parts.ts'
import { CODE, HINT, OUTLINE_BUTTON, T } from './tokens.ts'
import type { SyncStatus, WorkbenchSyncFace } from './workbenchSyncRemote.ts'

export function createSyncView(resolve: () => WorkbenchSyncFace | undefined, t: Translate) {
  return function SyncView(): ReactElement {
    const [status, setStatus] = useState<SyncStatus | null>(null)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const load = async (fetchRemote: boolean): Promise<void> => {
      const remote = resolve()
      if (remote === undefined) {
        setError(t('sync.unavailable'))
        return
      }
      setLoading(true)
      setError('')
      try {
        setStatus(await (fetchRemote ? remote.refresh() : remote.preview()))
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason))
      } finally {
        setLoading(false)
      }
    }

    useEffect(() => { void load(true) }, [])

    return h('div', { 'data-sync-view': '', style: { display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 880 } },
      h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: 12 } },
        h('div', { style: { flex: '1 1 auto' } },
          h('h2', { style: { margin: 0, fontSize: 18, fontWeight: 600 } }, t('sync')),
          h('div', { style: HINT }, t('sync.subtitle')),
        ),
        h('button', { type: 'button', disabled: loading, onClick: () => { void load(true) }, style: OUTLINE_BUTTON }, loading ? t('loading') : t('sync.refresh')),
      ),
      error ? notice(error, T.danger) : null,
      status === null && !error ? notice(t('loading'), T.text3) : null,
      status === null ? null : summary(status, t),
      status === null ? null : listSection(t('sync.localChanges'), status.files.map((file) => `${file.status}  ${file.path}`), t('sync.clean')),
      status === null ? null : listSection(t('sync.localCommits'), status.localCommits, t('sync.none')),
      status === null ? null : listSection(t('sync.remoteCommits'), status.remoteCommits, t('sync.none')),
    )
  }
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
