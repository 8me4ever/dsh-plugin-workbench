/**
 * The host page — every plugin this profile composes, and how far each got.
 *
 * This is the detail view behind the console's host card. It answers the one
 * question the console can only summarise: *which* plugin failed, and which are
 * disabled. A workbench you have to open a panel to discover a broken plugin in
 * is a worse workbench, but a plugin list on the home page is a worse home
 * page — hence a card and a page you can go Back from.
 *
 * Reads the host's read-only plugin inventory Remote; nothing is fetched
 * through a private RPC.
 */
import { createElement as h, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import { notice, statusStrip } from './parts.ts'
import { useStoreValue, type InventoryEntry, type InventoryStore } from './store.ts'
import { CODE, phaseColor, T } from './tokens.ts'

/** What the host page needs from the workbench. */
export interface HostViewFace {
  inventory: InventoryStore
}

/**
 * Build the host page component.
 * @param face - the shared inventory store.
 * @param t - bound translator.
 */
export function createHostView(face: HostViewFace, t: Translate) {
  return function HostView(): ReactElement {
    const state = useStoreValue(face.inventory)
    const entries = state.entries

    const counts = {
      total: entries.length,
      active: entries.filter((e) => e.fiberPhase === 'active').length,
      failed: entries.filter((e) => e.fiberPhase === 'failed').length,
      disabled: entries.filter((e) => !e.enabled).length,
    }

    // Breakage first, then working, then everything else — the order you would
    // want to read a status page in.
    const sorted = [...entries].sort((a, b) => rank(a) - rank(b) || a.moduleName.localeCompare(b.moduleName))

    return h(
      'div',
      { style: { display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 880 } },
      statusStrip(t, state, counts, () => { void face.inventory.refresh() }),
      pluginList(t, state, sorted),
    )
  }
}

/** Sort key for the plugin list: failed → active → rest. */
function rank(entry: InventoryEntry): number {
  if (entry.fiberPhase === 'failed') return 0
  if (entry.fiberPhase === 'active') return 1
  return 2
}

/** The plugin list, with its loading / error / empty states. */
function pluginList(
  t: Translate,
  state: { status: string; error: string },
  entries: readonly InventoryEntry[],
): ReactElement {
  if (state.status === 'error') return notice(state.error || t('error'), T.danger)
  if (entries.length === 0 && state.status === 'loading') return notice(t('loading'), T.text3)
  if (entries.length === 0) return notice(t('empty'), T.text3)
  return h('div', { 'data-plugin-list': '' }, ...entries.map((entry) => pluginRow(t, entry)))
}

/** One plugin row: module specifier, entry id, phase badge, disabled tag. */
function pluginRow(t: Translate, entry: InventoryEntry): ReactElement {
  const phase = entry.fiberPhase === null ? 'none' : String(entry.fiberPhase)
  return h(
    'div',
    {
      key: entry.entryId,
      'data-plugin': entry.entryId,
      style: {
        display: 'flex',
        alignItems: 'baseline',
        gap: 8,
        padding: '6px 0',
        borderBottom: `1px solid ${T.border1}`,
      },
    },
    h(
      'div',
      { style: { flex: '1 1 auto', minWidth: 0 } },
      h(
        'div',
        {
          style: {
            ...CODE,
            wordBreak: 'break-all',
            color: entry.enabled ? T.text1 : T.text3,
          },
        },
        entry.moduleName,
      ),
      h('div', { style: { color: T.textDim, fontSize: 11, wordBreak: 'break-all' } }, entry.entryId),
    ),
    entry.enabled
      ? null
      : h(
        'span',
        {
          style: {
            flex: '0 0 auto',
            fontSize: 11,
            color: T.text3,
            border: `1px solid ${T.border2}`,
            borderRadius: 4,
            padding: '0 4px',
          },
        },
        t('stat.disabled'),
      ),
    h(
      'span',
      { style: { flex: '0 0 auto', fontSize: 11, color: phaseColor(phase), whiteSpace: 'nowrap' } },
      t(`phase.${phase}`),
    ),
  )
}
