/**
 * Navigation history for the workbench panel.
 *
 * The workbench lives in the centre column now, so it needs the thing a browser
 * gives you the moment you start navigating inside a page: a stack with a
 * cursor, and two buttons that walk it. `back()` and `forward()` move the
 * cursor; a *new* navigation truncates everything after it, which is exactly
 * what makes Forward go dead after you take a different branch.
 *
 * Like the other stores here it is plain `get`/`subscribe`; the React binding
 * lives in `store.ts`.
 *
 * The store is created once per plugin, not per mount, so switching the centre
 * column away and back returns you to the view you were on — the same way a
 * browser tab keeps its history while you look at another tab.
 */
import { createValueStore, type ValueStore } from './store.ts'

/**
 * How deep the stack is allowed to get. Browsers keep far more, but nothing
 * here is worth an unbounded array, and nobody walks back 50 screens.
 */
const MAX_DEPTH = 50

/** The stack plus where in it we currently are. */
export interface HistoryState {
  readonly stack: readonly string[]
  /** Index of the current entry; always a valid index into `stack`. */
  readonly cursor: number
}

/** Observable view history with browser-like movement. */
export interface HistoryStore extends ValueStore<HistoryState> {
  /** The view id being shown. */
  current(): string
  /** Go to `viewId`, dropping any forward entries. A no-op for the current view. */
  push(viewId: string): void
  /** Step back one entry, if there is one. */
  back(): void
  /** Step forward one entry, if there is one. */
  forward(): void
  canBack(): boolean
  canForward(): boolean
  /** Throw the stack away and start again at `viewId`. */
  reset(viewId: string): void
}

/**
 * Create a history store.
 * @param initial - the view to start on (the console, in practice).
 */
export function createHistoryStore(initial: string): HistoryStore {
  const store = createValueStore<HistoryState>({ stack: [initial], cursor: 0 })

  /** Move the cursor without touching the stack. */
  const step = (delta: number): void => {
    const state = store.get()
    const cursor = state.cursor + delta
    if (cursor < 0 || cursor >= state.stack.length) return
    store.set({ stack: state.stack, cursor })
  }

  return {
    get: store.get,
    set: store.set,
    subscribe: store.subscribe,
    current: () => {
      const state = store.get()
      return state.stack[state.cursor] ?? initial
    },
    push(viewId) {
      const state = store.get()
      // Re-selecting where you already are must not fill the stack with copies
      // — otherwise Back would appear to do nothing.
      if (state.stack[state.cursor] === viewId) return
      const kept = state.stack.slice(0, state.cursor + 1)
      kept.push(viewId)
      const overflow = Math.max(0, kept.length - MAX_DEPTH)
      const stack = overflow > 0 ? kept.slice(overflow) : kept
      store.set({ stack, cursor: stack.length - 1 })
    },
    back: () => step(-1),
    forward: () => step(1),
    canBack: () => store.get().cursor > 0,
    canForward: () => {
      const state = store.get()
      return state.cursor < state.stack.length - 1
    },
    reset(viewId) {
      store.set({ stack: [viewId], cursor: 0 })
    },
  }
}
