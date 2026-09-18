/**
 * Small view atoms shared by the console and the host page.
 *
 * Both of them report on the same host read, so the counters, the read time
 * and the "no entries yet" branches live here instead of being written twice
 * and drifting.
 */
import { createElement as h, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import type { InventoryState } from './store.ts'
import { HINT, OUTLINE_BUTTON, SECTION_TITLE, T } from './tokens.ts'

/** The four counters, in the order they read best. */
export interface Counts {
  readonly total: number
  readonly active: number
  readonly failed: number
  readonly disabled: number
}

/** A section heading with optional right-aligned content. */
export function sectionHeader(title: string, right: (ReactElement | null)[] = []): ReactElement {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        paddingBottom: 6,
        borderBottom: `1px solid ${T.border1}`,
      },
    },
    h('span', { style: { ...SECTION_TITLE, flex: '1 1 auto' } }, title),
    ...right.filter((node): node is ReactElement => node !== null),
  )
}

/** A single muted status line — the loading / error / empty branches. */
export function notice(text: string, color: string): ReactElement {
  return h(
    'div',
    { style: { padding: '12px 0', color, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' } },
    text,
  )
}

/**
 * One line of host status: the four counters, when it was read, and a reread.
 *
 * A strip rather than four cards: the numbers are context for the cards below,
 * not something to navigate into, and the console's job is to keep what you can
 * click on visually distinct from what you can only read.
 */
export function statusStrip(
  t: Translate,
  state: InventoryState,
  counts: Counts,
  onRefresh: () => void,
): ReactElement {
  const cells: [string, number, string][] = [
    [t('stat.total'), counts.total, T.text1],
    [t('stat.active'), counts.active, T.ok],
    [t('stat.failed'), counts.failed, counts.failed > 0 ? T.danger : T.textDim],
    [t('stat.disabled'), counts.disabled, counts.disabled > 0 ? T.text3 : T.textDim],
  ]
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 16,
        padding: '9px 12px',
        borderRadius: 10,
        border: `1px solid ${T.border1}`,
        background: T.bgLayer2,
      },
    },
    ...cells.map(([label, value, color]) => h(
      'div',
      { key: label, style: { display: 'flex', alignItems: 'baseline', gap: 6 } },
      h('span', { style: { fontSize: 11, color: T.text3 } }, label),
      h('span', { style: { fontSize: 16, fontWeight: 500, lineHeight: 1.2, color } }, String(value)),
    )),
    h('span', { style: { flex: '1 1 auto' } }),
    state.readAt > 0
      ? h('span', { key: 'at', style: HINT }, `${t('readAt')} ${new Date(state.readAt).toLocaleTimeString()}`)
      : null,
    h('button', { key: 'refresh', type: 'button', onClick: onRefresh, style: OUTLINE_BUTTON }, t('refresh')),
  )
}
