/**
 * View ids, the panel key, and slot naming — shared by the chrome, the console
 * and the content area.
 *
 * A view id is one of three things:
 *
 *   - the console (`control-room`), the workbench's home;
 *   - the host inventory page (`host`);
 *   - a project slot (`slot:<index>`).
 *
 * Keeping the encoding, the labels and the validity check in one place means
 * the chrome, the console's cards and the content switch can never disagree
 * about what "slot 2" is — or about whether an id found in the history still
 * resolves to anything.
 */
import type { Translate } from './i18n.ts'

/** The console view. Reserved: projects must not use this id. */
export const CONTROL_ROOM_ID = 'control-room'

/** The host plugin-inventory view. Reserved, like the console. */
export const HOST_ID = 'host'
export const SYNC_ID = 'sync'

/**
 * The `main` slot key this plugin claims — and, deliberately, the id of the
 * sidebar entry that selects it.
 *
 * The layout dispatches the central panel by the id the sidebar row was
 * registered with (`renderSlot('main', {}, { entryKey: activePanelId })`), so
 * one string has to serve as both. Keeping it in one constant is what stops the
 * entry and the panel from drifting apart.
 */
export const PANEL_ID = 'workbench'

/** View id of the project slot at `index` (0-based). */
export function slotViewId(index: number): string {
  return `slot:${index}`
}

/**
 * Decode a view id back to a slot index.
 * @returns the index, or null when the id is not a slot (e.g. the console).
 */
export function slotIndexOf(viewId: string): number | null {
  if (!viewId.startsWith('slot:')) return null
  const index = Number.parseInt(viewId.slice(5), 10)
  return Number.isInteger(index) && index >= 0 ? index : null
}

/** 1 → "01". */
export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/**
 * How an unclaimed slot is named: "项目 01".
 * A filled slot is named by the project itself (`project.title()`), not here.
 */
export function slotLabel(index: number, t: Translate): string {
  return `${t('slot')} ${pad2(index + 1)}`
}

/**
 * Does this workbench know what to draw for `viewId`?
 *
 * The history outlives any single render, so it can hold an id that no longer
 * resolves — a slot list that shrank in a rebuild is the realistic case. Asked
 * before drawing, rather than assumed.
 */
export function isKnownView(viewId: string, slotCount: number): boolean {
  if (viewId === CONTROL_ROOM_ID || viewId === HOST_ID || viewId === SYNC_ID) return true
  const index = slotIndexOf(viewId)
  return index !== null && index < slotCount
}

/** Repair an id that no longer resolves by falling back to the console. */
export function clampViewId(viewId: string, slotCount: number): string {
  return isKnownView(viewId, slotCount) ? viewId : CONTROL_ROOM_ID
}
