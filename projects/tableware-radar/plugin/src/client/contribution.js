/**
 * Client-side contribution descriptors for the `tablewareRadar` data face.
 *
 * The browser module table only provides `react`, so `zod` is **bundled into the client
 * bundle** (esbuild) — the descriptors carry strict codecs identical to the host manifest.
 * The gateway rejects any descriptor whose codec is not `mode: 'strict'`, and strictly
 * matches `parameters.length`, so both methods are 0-parameter.
 *
 * Reusing `METHODS` from `../schemas.js` guarantees the two halves never drift.
 */
import { METHODS } from '../schemas.js'

/** Hand-written contribution: the namespace the page mounts via `ctx.remote.$mount`. */
export const contribution = {
  package: 'dsh-tableware-radar',
  descriptors: METHODS,
}

export default contribution
