/**
 * The workbench panel.
 *
 * Slot: `main`, keyed `workbench` — "Central panel selected by sidebar entry
 * id". The sidebar entry registered under the same id is what puts this panel
 * in the centre column; `ctx.layout.selectPanel('workbench')` is what the entry
 * calls. There is no overlay and no modal: the workbench *is* the main view
 * while it is selected, and the Conversation is one sidebar click away.
 *
 * The panel owns three things and nothing else: the chrome (browser-like Back /
 * Forward plus a breadcrumb), the history, and which view is showing. Anything
 * that looks like "content" belongs either to the built-in console / host page
 * or to one of the projects.
 *
 * It also reports its own presence: mounting sets `shown` and unmounting clears
 * it, so the sidebar entry knows whether it is the selected panel without
 * anyone having to mirror the layout's state into a second copy.
 */
import { createElement as h, useEffect, type ReactElement } from 'react'
import { createControlRoom } from './ControlRoom.ts'
import { createHostView } from './HostView.ts'
import type { HistoryState, HistoryStore } from './history.ts'
import type { Translate } from './i18n.ts'
import { createProjectHost } from './projects/host.ts'
import type { ProjectContext, ProjectSlot } from './projects/types.ts'
import { useStoreValue, type ValueStore } from './store.ts'
import { OUTLINE_BUTTON, SCROLL, T } from './tokens.ts'
import { clampViewId, CONTROL_ROOM_ID, HOST_ID, slotIndexOf, slotLabel, slotViewId } from './views.ts'

/** Everything the panel needs from the plugin entry point. */
export interface WorkbenchFace {
  /**
   * True while this panel occupies the centre. Written here, read by the
   * sidebar entry — deriving it from the mount is what keeps the two honest
   * without a second source of truth.
   */
  shown: ValueStore<boolean>
  /** View history; survives leaving the panel and coming back. */
  history: HistoryStore
  /** The project slots, in display order. Length is whatever slots.ts declares. */
  projects: readonly ProjectSlot[]
  /** Handed to every project. */
  projectCtx: ProjectContext
  /** Hand the centre column back to the Conversation. */
  close(): void
}

/**
 * Build the workbench panel.
 * @param face - stores and slot list from the plugin entry point.
 * @param t - bound translator.
 */
export function createWorkbench(face: WorkbenchFace, t: Translate) {
  const ProjectHost = createProjectHost(face.projectCtx, t)
  // The console and the host page subscribe to the stores themselves, so
  // neither of them takes any props beyond what its factory closed over.
  const ControlRoom = createControlRoom({
    inventory: face.projectCtx.inventory,
    projects: face.projects,
    onOpen: (id) => face.history.push(id),
  }, t)
  const HostView = createHostView({ inventory: face.projectCtx.inventory }, t)

  return function Workbench(): ReactElement {
    const history = useStoreValue(face.history)

    // Announce that this panel is the selected one, for as long as it is.
    useEffect(() => {
      face.shown.set(true)
      return () => { face.shown.set(false) }
    }, [])

    // Read the host on every mount, so the console never shows a snapshot older
    // than the last time you looked at it. De-duplicated in the store, so
    // switching back and forth cannot stack reads up.
    useEffect(() => {
      void face.projectCtx.inventory.refresh()
    }, [])

    // Alt+Left / Alt+Right, the shortcut browsers use for the same buttons.
    useEffect(() => {
      const onKey = (event: KeyboardEvent): void => {
        if (!event.altKey) return
        if (event.key === 'ArrowLeft') face.history.back()
        else if (event.key === 'ArrowRight') face.history.forward()
      }
      window.addEventListener('keydown', onKey)
      return () => window.removeEventListener('keydown', onKey)
    }, [])

    // The history can outlive the shape it was recorded against: a slot list
    // that shrank in a rebuild leaves an id that no longer resolves. Repaired on
    // read rather than trusted.
    const viewId = clampViewId(history.stack[history.cursor] ?? CONTROL_ROOM_ID, face.projects.length)

    return h(
      'div',
      {
        'data-workbench': '',
        'aria-label': t('title'),
        style: {
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          minHeight: 0,
          overflow: 'hidden',
          background: T.bgBase,
          color: T.text1,
          fontFamily: T.font,
          fontSize: 13,
        },
      },
      chrome(t, face, history, viewId),
      h(
        'div',
        {
          // Which view is in the body, as an attribute: the headless smoke test
          // cannot see through the component boundary, and neither can you when
          // inspecting the live DOM.
          'data-view': viewId,
          style: { flex: '1 1 auto', minHeight: 0, padding: '20px 24px 28px', ...SCROLL },
        },
        body(viewId, face, { ControlRoom, HostView, ProjectHost }),
      ),
    )
  }
}

/** The three view components, built once by the panel factory. */
interface Views {
  ControlRoom: () => ReactElement
  HostView: () => ReactElement
  ProjectHost: (props: { slot: ProjectSlot; index: number }) => ReactElement
}

/**
 * Which view is showing.
 *
 * Rendered through `h`, never called as a function: these components hold hook
 * state, so they have to be their own component in the tree. The key makes
 * switching views a remount, which is what we want — a project should not
 * inherit the previous view's state.
 */
function body(viewId: string, face: WorkbenchFace, views: Views): ReactElement {
  if (viewId === HOST_ID) return h(views.HostView, { key: HOST_ID })
  const index = slotIndexOf(viewId)
  if (index === null) return h(views.ControlRoom, { key: CONTROL_ROOM_ID })
  return h(views.ProjectHost, {
    key: slotViewId(index),
    slot: face.projects[index] ?? null,
    index,
  })
}

/** Title of a view, for the breadcrumb. */
function viewTitle(t: Translate, face: WorkbenchFace, viewId: string): string {
  if (viewId === HOST_ID) return t('host')
  const index = slotIndexOf(viewId)
  if (index === null) return t('console')
  const slot = face.projects[index]
  return slot !== null && slot !== undefined ? slot.title() : slotLabel(index, t)
}

/**
 * The top bar: Back, Forward, the breadcrumb, and the way out.
 *
 * Every destination the console offers is one click deep, so two segments are
 * the most the crumb can ever hold — but the crumb is still the thing that
 * answers "where am I", which the back button alone cannot.
 */
function chrome(
  t: Translate,
  face: WorkbenchFace,
  history: HistoryState,
  viewId: string,
): ReactElement {
  const atConsole = viewId === CONTROL_ROOM_ID
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '9px 14px',
        borderBottom: `1px solid ${T.border1}`,
        flex: '0 0 auto',
      },
    },
    navButton('back', t('back'), history.cursor > 0, () => face.history.back(), arrow('M10.4 3.2 5.6 8l4.8 4.8')),
    navButton(
      'forward',
      t('forward'),
      history.cursor < history.stack.length - 1,
      () => face.history.forward(),
      arrow('M5.6 3.2 10.4 8l-4.8 4.8'),
    ),
    h('span', { style: { width: 1, height: 18, background: T.border1, margin: '0 6px' } }),

    atConsole
      ? crumb(t('console'), CONTROL_ROOM_ID, null)
      : crumb(t('console'), CONTROL_ROOM_ID, () => face.history.push(CONTROL_ROOM_ID)),
    atConsole ? null : crumbSeparator(),
    atConsole ? null : crumb(viewTitle(t, face, viewId), viewId, null),

    h('span', { style: { flex: '1 1 auto' } }),
    h(
      'button',
      { type: 'button', title: t('exit'), onClick: () => face.close(), style: OUTLINE_BUTTON },
      t('exit'),
    ),
  )
}

/** One breadcrumb segment; the last one is not a link. */
function crumb(label: string, viewId: string, onSelect: (() => void) | null): ReactElement {
  return h(
    'button',
    {
      key: viewId,
      type: 'button',
      'data-crumb': viewId,
      'aria-current': onSelect === null ? 'page' : undefined,
      onClick: onSelect ?? undefined,
      style: {
        border: '1px solid transparent',
        borderRadius: 6,
        background: 'transparent',
        color: onSelect === null ? T.text1 : T.text2,
        font: 'inherit',
        fontSize: 12.5,
        fontWeight: onSelect === null ? 500 : 400,
        padding: '2px 6px',
        cursor: onSelect === null ? 'default' : 'pointer',
      },
    },
    label,
  )
}

/** The › between two breadcrumb segments. */
function crumbSeparator(): ReactElement {
  return h(
    'span',
    { key: 'sep', style: { color: T.textDim, fontSize: 11, userSelect: 'none' } },
    '›',
  )
}

/** A Back / Forward button. Disabled rather than hidden, so the pair never moves. */
function navButton(
  id: string,
  label: string,
  enabled: boolean,
  onClick: () => void,
  glyph: ReactElement,
): ReactElement {
  return h(
    'button',
    {
      type: 'button',
      'data-nav': id,
      title: label,
      'aria-label': label,
      'aria-disabled': enabled ? undefined : 'true',
      disabled: !enabled,
      onClick,
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 26,
        height: 26,
        border: '1px solid transparent',
        borderRadius: 6,
        background: 'transparent',
        color: enabled ? T.text2 : T.textDim,
        font: 'inherit',
        padding: 0,
        cursor: enabled ? 'pointer' : 'default',
      },
    },
    glyph,
  )
}

/** A 16×16 stroked arrow path. */
function arrow(d: string): ReactElement {
  return h(
    'svg',
    {
      width: 15,
      height: 15,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 1.5,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'aria-hidden': true,
    },
    h('path', { d }),
  )
}
