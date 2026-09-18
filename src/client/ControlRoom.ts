/**
 * The console — the workbench's home view, and the only place that lists
 * everything the workbench can open.
 *
 * It is deliberately a *card* surface rather than a nav rail: every card is one
 * destination, clicking one is a navigation (so it pushes onto the history and
 * Back brings you here), and the shapes you can click on never mix with the
 * numbers you can only read. The host status is the one exception, and it is
 * rendered as a strip above the grid precisely because it is not a destination
 * of its own — the plugin list it summarises has a card.
 *
 * Everything here reads the host's read-only plugin inventory Remote; nothing
 * is fetched through a private RPC.
 */
import { createElement as h, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import { notice, sectionHeader, statusStrip } from './parts.ts'
import type { ProjectSlot } from './projects/types.ts'
import { useStoreValue, type InventoryStore } from './store.ts'
import { HINT, T } from './tokens.ts'
import { HOST_ID, slotLabel, slotViewId } from './views.ts'

/** The four counters, as `parts.statusStrip` wants them. */
interface Counts {
  readonly total: number
  readonly active: number
  readonly failed: number
  readonly disabled: number
}

/** What the console needs from the workbench. */
export interface ControlRoomFace {
  inventory: InventoryStore
  projects: readonly ProjectSlot[]
  /** Open a view. Pushes onto the history, so Back comes back here. */
  onOpen(id: string): void
}

/**
 * Build the console component.
 * @param face - stores and callbacks from the workbench.
 * @param t - bound translator.
 */
export function createControlRoom(face: ControlRoomFace, t: Translate) {
  return function ControlRoom(): ReactElement {
    const state = useStoreValue(face.inventory)
    const entries = state.entries

    const counts = {
      total: entries.length,
      active: entries.filter((e) => e.fiberPhase === 'active').length,
      failed: entries.filter((e) => e.fiberPhase === 'failed').length,
      disabled: entries.filter((e) => !e.enabled).length,
    }
    const claimed = face.projects.filter((p) => p !== null && p !== undefined).length

    return h(
      'div',
      { style: { display: 'flex', flexDirection: 'column', gap: 22, maxWidth: 880 } },

      statusStrip(t, state, counts, () => { void face.inventory.refresh() }),

      // A failed read is worth saying out loud on the console: the counters above
      // would otherwise read as "this profile really has zero plugins", and the
      // host card would send you to a page that says nothing either. The cards
      // below stay usable — they do not depend on the read.
      state.status === 'error'
        ? notice(state.error || t('error'), T.danger)
        : entries.length === 0 && state.status === 'loading'
          ? notice(t('loading'), T.text3)
          : null,

      section(
        t('section.projects'),
        [`${claimed} / ${face.projects.length}`],
        cardGrid(face.projects.map((slot, index) => projectCard(t, slot, index, face.onOpen))),
      ),

      section(
        t('section.host'),
        [],
        cardGrid([hostCard(t, counts, face.onOpen)]),
      ),
    )
  }
}

/** A titled block, with an optional right-aligned count. */
function section(title: string, meta: string[], children: ReactElement): ReactElement {
  return h(
    'section',
    { style: { display: 'flex', flexDirection: 'column' } },
    sectionHeader(
      title,
      meta.map((value) => h('span', { key: value, style: HINT }, value)),
    ),
    children,
  )
}

/** The responsive card grid: as many columns as the column width allows. */
function cardGrid(cards: ReactElement[]): ReactElement {
  return h(
    'div',
    {
      style: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(216px, 1fr))',
        gap: 10,
        marginTop: 12,
      },
    },
    ...cards,
  )
}

/**
 * One project card — claimed, or still free.
 *
 * A free card is not disabled: clicking it opens the reserved-slot page, which
 * is the only place that explains how to fill it. A card you cannot click tells
 * you nothing.
 */
function projectCard(
  t: Translate,
  slot: ProjectSlot,
  index: number,
  onOpen: (id: string) => void,
): ReactElement {
  const claimed = slot !== null && slot !== undefined
  const title = claimed ? slot.title() : slotLabel(index, t)
  const summary = claimed && typeof slot.summary === 'function' ? slot.summary() : t('slot.free.summary')

  return card({
    viewId: slotViewId(index),
    claimed,
    eyebrow: String(index + 1).padStart(2, '0'),
    title,
    summary,
    tag: claimed ? t('slot.filled') : t('slot.free'),
    tagColor: claimed ? T.ok : T.text3,
    icon: claimed && typeof slot.icon === 'function' ? slot.icon() : null,
    onOpen,
  })
}

/** The host card: how the composed profile is doing, and a way into the list. */
function hostCard(t: Translate, counts: Counts, onOpen: (id: string) => void): ReactElement {
  const summary = counts.failed > 0
    ? `${counts.active} / ${counts.total} ${t('stat.active')} · ${counts.failed} ${t('stat.failed')}`
    : `${counts.active} / ${counts.total} ${t('stat.active')}`
  return card({
    viewId: HOST_ID,
    claimed: true,
    eyebrow: '—',
    title: t('host'),
    summary,
    tag: counts.failed > 0 ? t('stat.failed') : t('slot.filled'),
    tagColor: counts.failed > 0 ? T.danger : T.text3,
    icon: hostGlyph(),
    onOpen,
  })
}

/** The one card shell, so every destination looks the same. */
function card(props: {
  viewId: string
  claimed: boolean
  eyebrow: string
  title: string
  summary: string
  tag: string
  tagColor: string
  icon: ReactElement | null
  onOpen: (id: string) => void
}): ReactElement {
  return h(
    'button',
    {
      key: props.viewId,
      type: 'button',
      // Stable hook for the headless smoke test and the browser check.
      'data-card': props.viewId,
      'data-claimed': props.claimed ? 'yes' : 'no',
      onClick: () => props.onOpen(props.viewId),
      style: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        gap: 6,
        width: '100%',
        boxSizing: 'border-box',
        textAlign: 'left',
        padding: '11px 13px 12px',
        borderRadius: 10,
        // Dashed while free: the outline is the only thing telling you this
        // card is a placeholder rather than a project.
        border: `1px ${props.claimed ? 'solid' : 'dashed'} ${props.claimed ? T.border1 : T.border2}`,
        background: T.bgLayer1,
        color: 'inherit',
        font: 'inherit',
        cursor: 'pointer',
      },
    },
    h(
      'div',
      { style: { display: 'flex', alignItems: 'center', gap: 8, width: '100%' } },
      props.icon,
      h('span', { style: { fontFamily: T.mono, fontSize: 11, color: T.textDim } }, props.eyebrow),
      h(
        'span',
        {
          style: {
            flex: '1 1 auto',
            fontSize: 13,
            fontWeight: 500,
            color: props.claimed ? T.text1 : T.text2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          },
        },
        props.title,
      ),
      h('span', { style: { flex: '0 0 auto', fontSize: 11, color: props.tagColor } }, props.tag),
      chevron(),
    ),
    h('div', { style: { ...HINT, fontSize: 11.5, minHeight: 34 } }, props.summary),
  )
}

/** A right-pointing chevron: the "this opens something" affordance. */
function chevron(): ReactElement {
  return h(
    'svg',
    {
      width: 12,
      height: 12,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 1.5,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'aria-hidden': true,
      style: { flex: '0 0 auto', color: T.textDim },
    },
    h('path', { d: 'M6.2 3.6 10.6 8l-4.4 4.4' }),
  )
}

/** Glyph for the host card: a stack of layers. */
function hostGlyph(): ReactElement {
  return h(
    'svg',
    {
      width: 14,
      height: 14,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 1.3,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'aria-hidden': true,
      style: { flex: '0 0 auto', color: T.text3 },
    },
    h('path', { d: 'M8 2.2 14 5.4 8 8.6 2 5.4z' }),
    h('path', { d: 'M2.6 8.4 8 11.3l5.4-2.9' }),
    h('path', { d: 'M2.6 11.2 8 14.1l5.4-2.9' }),
  )
}
