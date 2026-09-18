/**
 * dsh-plugin-workbench — host half.
 *
 * This feature is UI-only: every pixel the user sees is contributed by the
 * client half in `src/client`. This half exists because the profile's bundle
 * list mounts a package by name, and the cordis loader resolves that name to
 * this module — so it has to be a valid plugin.
 *
 * It deliberately declares no `inject`: the host half wants nothing from the
 * host, and an empty dependency set means the entry can never be stuck
 * waiting for a service that a given profile does not compose.
 *
 * If a future project needs host-side data (files, network, process state),
 * that is where a host half earns its keep: add `@Remote` methods here and
 * call them from the project through `ctx.remote.<namespace>`.
 */
import type { Context } from '@deepseek-ai/cordis'

/** Cordis plugin name — also the client bundle id and the patch row id. */
export const name = 'dsh-plugin-workbench'

/** No host-side service dependencies. */
export const inject: string[] = []

/**
 * Mount the host half.
 * @param ctx - host cordis context.
 */
export function apply(ctx: Context): void {
  ctx.logger.info('[dsh-plugin-workbench] host half mounted — UI comes from the client half')
}
