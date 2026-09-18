/**
 * The sidebar-foot entry that selects the workbench panel.
 *
 * Slot: `sidebar.footer.action` (list, root) — "optional actions beside
 * Settings at the sidebar foot". Owner props are just `{ wide }`: false means
 * the column is a 56px rail, so we render the glyph alone and let the label
 * ride the wide state.
 *
 * This button does not open a window: it selects the panel the layout already
 * knows about (`ctx.layout.selectPanel`), so the workbench takes over the
 * centre column and clicking again hands the centre back to the Conversation.
 * Which of the two states we are in is told to us by the panel itself, via the
 * `shown` store — see `Workbench.ts`.
 *
 * The entry is a component *factory*: closing over the stores and the bound
 * translator keeps the registration face tiny and avoids depending on props
 * the slot may or may not project.
 */
import { createElement as h, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import { T } from './tokens.ts'
import { useStoreValue, type InventoryStore, type ValueStore } from './store.ts'

/** What the entry needs from the plugin entry point. */
export interface TriggerFace {
  /** Whether the workbench is the selected main panel. */
  shown: ValueStore<boolean>
  inventory: InventoryStore
  /** Select this panel's seat in the centre, or leave it. */
  toggle(show: boolean): void
}

/**
 * Build the entry component.
 * @param face - stores shared with the panel.
 * @param t - bound translator.
 */
export function createTrigger(face: TriggerFace, t: Translate) {
  return function Trigger(props: { wide?: boolean }): ReactElement {
    const shown = useStoreValue(face.shown)
    const entries = useStoreValue(face.inventory).entries
    const wide = props?.wide === true

    // The only thing about the host worth surfacing at a glance is breakage:
    // a workbench you have to open to discover a failed plugin is a worse
    // workbench.
    const failed = entries.filter((e) => e.fiberPhase === 'failed').length

    return h(
      'button',
      {
        type: 'button',
        title: t('action'),
        'aria-label': t('action'),
        'aria-current': shown ? 'page' : undefined,
        'aria-pressed': shown ? 'true' : 'false',
        onClick: () => face.toggle(!shown),
        style: {
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: wide ? '100%' : 32,
          height: 32,
          padding: wide ? '0 8px' : 0,
          justifyContent: wide ? 'flex-start' : 'center',
          border: '1px solid transparent',
          borderRadius: 8,
          // Selected reads like the other sidebar panel rows do: a filled
          // surface, not just a colour change.
          background: shown ? T.bgHover : 'transparent',
          color: failed > 0 ? T.danger : shown ? T.text1 : T.text2,
          font: 'inherit',
          fontSize: 13,
          cursor: 'pointer',
        },
      },
      glyph(16),
      wide ? h('span', { style: { flex: '1 1 auto', textAlign: 'left' } }, t('action')) : null,
      failed > 0
        ? h(
          'span',
          {
            style: {
              flex: '0 0 auto',
              minWidth: 18,
              height: 18,
              padding: '0 5px',
              boxSizing: 'border-box',
              borderRadius: 9,
              background: T.bgHover,
              color: T.danger,
              fontSize: 11,
              lineHeight: '18px',
              textAlign: 'center',
            },
          },
          String(failed),
        )
        : null,
    )
  }
}

/**
 * A workbench glyph: a frame with a side rail and a couple of content blocks.
 * Inline so the plugin carries no icon assets and inherits `currentColor`.
 */
function glyph(size: number): ReactElement {
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 1.3,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'aria-hidden': true,
      style: { flex: '0 0 auto' },
    },
    h('rect', { x: 1.6, y: 2.6, width: 12.8, height: 10.8, rx: 1.6 }),
    h('path', { d: 'M6.2 2.9v10.2' }),
    h('path', { d: 'M8.2 6.1h4.2' }),
    h('path', { d: 'M8.2 9.1h2.8' }),
  )
}
