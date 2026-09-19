/**
 * Shared strict codecs for the `tablewareRadar` data face.
 *
 * Imported by BOTH halves:
 *   - host  half → `src/typert.host.js`      (node resolves `zod` from node_modules)
 *   - client half → `src/client/contribution.js` (esbuild bundles `zod` into the browser bundle)
 *
 * The gateway's `requireStrictDescriptor` demands every parameter/context codec use
 * `mode: 'strict'`. Both methods here are **0-parameter** (see docs/ARCHITECTURE.md §3.4),
 * so there are no parameter codecs to declare — only result codecs.
 *
 * The analysis schema is intentionally permissive on nested payloads
 * (`z.record(z.string(), z.unknown())`) so it never strips data the page needs;
 * the top-level shape is pinned so a malformed file fails loudly instead of silently.
 */
import { z } from 'zod'

/** Top-level keys of `data/analysis.json` (see ARCHITECTURE §3.2). */
export const analysisSchema = z.object({
  generated_at: z.string(),
  dimension_set_version: z.string(),
  sample: z.record(z.string(), z.unknown()),
  dimensions: z.array(z.record(z.string(), z.unknown())),
  by_asin: z.array(z.record(z.string(), z.unknown())),
  top_praise: z.array(z.record(z.string(), z.unknown())),
  top_complaint: z.array(z.record(z.string(), z.unknown())),
  opportunities: z.array(z.record(z.string(), z.unknown())),
  selection_priority: z.array(z.record(z.string(), z.unknown())),
  risk_flags: z.array(z.record(z.string(), z.unknown())),
  filters: z.record(z.string(), z.unknown()),
  other_topics: z.array(z.record(z.string(), z.unknown())),
  data_quality: z.record(z.string(), z.unknown()),
})

/** `getStatus()` return shape. */
export const statusSchema = z.object({
  present: z.boolean(),
  path: z.string(),
  mtimeMs: z.number(),
  bytes: z.number(),
  generatedAt: z.union([z.string(), z.null()]),
})

/** `getAnalysis()` returns `Analysis | null` (file absent → null). */
export const analysisResultCodec = {
  mode: 'strict',
  typeSymbol: 'dsh-tableware-radar#Analysis',
  schema: z.union([analysisSchema, z.null()]),
}

/** `getStatus()` result codec. */
export const statusResultCodec = {
  mode: 'strict',
  typeSymbol: 'dsh-tableware-radar#Status',
  schema: statusSchema,
}

/** The two methods, shared verbatim by the host TYPERT manifest and the client contribution. */
export const METHODS = [
  {
    id: 'dsh-tableware-radar#tablewareRadar/getAnalysis',
    service: 'tablewareRadar',
    namespace: 'tablewareRadar',
    method: 'getAnalysis',
    invocation: { kind: 'direct' },
    parameters: [],
    result: analysisResultCodec,
  },
  {
    id: 'dsh-tableware-radar#tablewareRadar/getStatus',
    service: 'tablewareRadar',
    namespace: 'tablewareRadar',
    method: 'getStatus',
    invocation: { kind: 'direct' },
    parameters: [],
    result: statusResultCodec,
  },
]
