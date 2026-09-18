/**
 * Shared state for the workbench.
 *
 * The sidebar entry, the workbench frame and every project read the same two
 * things: whether the workbench is open, and which view is selected. They are
 * all registered from the same `apply`, so module-scoped stores are the
 * cheapest way to connect them — no wider inject face, no framework state
 * service, no context provider to thread through slot boundaries.
 *
 * The store is plain `get`/`subscribe`, and the React binding below adapts it
 * with `useState` + `useEffect` rather than `useSyncExternalStore`, so the
 * bundle stays compatible with whatever React 18 build the client composes.
 */
import { useEffect, useState } from 'react'

/** Lifecycle state of an entry's root fiber, or null when it has no live root. */
export type FiberPhase = 'pending' | 'loading' | 'active' | 'failed' | 'unloading' | null

/** One non-group Loader entry, as the host inventory reports it. */
export interface InventoryEntry {
  readonly entryId: string
  readonly moduleName: string
  readonly enabled: boolean
  readonly fiberPhase: FiberPhase
}

/** Minimal observable value. */
export interface ValueStore<T> {
  get(): T
  set(value: T): void
  subscribe(listener: () => void): () => void
}

/** Create an observable value. */
export function createValueStore<T>(initial: T): ValueStore<T> {
  let value = initial
  const listeners = new Set<() => void>()
  return {
    get: () => value,
    set(next) {
      if (next === value) return
      value = next
      for (const listener of listeners) listener()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    },
  }
}

/** Open/closed state of the workbench. */
export type OpenStore = ValueStore<boolean>

/** One inventory read's outcome, as the control room renders it. */
export interface InventoryState {
  readonly status: 'idle' | 'loading' | 'ready' | 'error'
  readonly entries: readonly InventoryEntry[]
  /** Epoch milliseconds of the last successful read, or 0. */
  readonly readAt: number
  readonly error: string
}

/** Inventory holder: remembers the last snapshot and de-duplicates reads. */
export interface InventoryStore extends ValueStore<InventoryState> {
  /** Re-read the host inventory. Concurrent calls share one in-flight read. */
  refresh(): Promise<void>
}

/**
 * Build the inventory store around a reader supplied by the plugin entry.
 * @param read - performs one host read and returns the entries.
 */
export function createInventoryStore(read: () => Promise<readonly InventoryEntry[]>): InventoryStore {
  const store = createValueStore<InventoryState>({ status: 'idle', entries: [], readAt: 0, error: '' })
  let inFlight: Promise<void> | null = null

  const refresh = (): Promise<void> => {
    if (inFlight !== null) return inFlight
    store.set({ ...store.get(), status: 'loading' })
    inFlight = read()
      .then((entries) => {
        store.set({ status: 'ready', entries, readAt: Date.now(), error: '' })
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        const previous = store.get()
        store.set({ status: 'error', entries: previous.entries, readAt: previous.readAt, error: message })
      })
      .finally(() => { inFlight = null })
    return inFlight
  }

  return {
    get: store.get,
    set: store.set,
    subscribe: store.subscribe,
    refresh,
  }
}

/** Subscribe a component to a store value. */
export function useStoreValue<T>(store: ValueStore<T>): T {
  const [value, setValue] = useState<T>(store.get())
  useEffect(() => store.subscribe(() => setValue(store.get())), [store])
  return value
}
