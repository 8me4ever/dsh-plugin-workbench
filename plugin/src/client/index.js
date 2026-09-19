/**
 * dsh-tableware-radar — client half.
 *
 * Mounts the `tablewareRadar` remote contribution into the web profile's API gateway so the
 * workbench project 02 page can call `ctx.remote.tablewareRadar.getAnalysis()/getStatus()`.
 *
 * Per ARCHITECTURE §1.6 (U3): inject `['remote']` first; only add `'typert'` if the host
 * raises `cannot get property "typert" without inject`.
 */
import { contribution } from './contribution.js'

/** Cordis plugin name — matches the host half and the patch row id. */
export const name = 'dsh-tableware-radar'

/** Client-side service dependency: the remote (API gateway) facade. */
export const inject = ['remote']

/**
 * Mount the client half.
 * @param {object} ctx client cordis context.
 */
export async function apply(ctx) {
  const dispose = await ctx.remote.$mount(contribution)
  ctx.effect(
    () => () => {
      if (typeof dispose === 'function') dispose()
    },
    'dsh-tableware-radar: remote contribution',
  )
}

export default { name, inject, apply }
