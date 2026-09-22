/** Client gateway descriptors for the two data faces owned by this package. */
import { z } from 'zod'

const strict = (typeSymbol: string, schema: z.ZodType) => ({ mode: 'strict', typeSymbol, schema })
const parameter = (name: string, schema: z.ZodType) => ({
  name,
  wire: name,
  source: 'json',
  codec: strict(`dsh-plugin-workbench#${name}`, schema),
})

const job = z.record(z.string(), z.unknown())
const analysis = z.record(z.string(), z.unknown())
const syncStatus = z.object({
  branch: z.string(),
  isMain: z.boolean(),
  ahead: z.number(),
  behind: z.number(),
  files: z.array(z.object({ path: z.string(), status: z.string(), tracked: z.boolean(), bytes: z.number(), blocker: z.string().optional() })),
  localCommits: z.array(z.string()),
  remoteCommits: z.array(z.string()),
  blockers: z.array(z.string()),
  fetchedAt: z.string(),
})
const commitPreview = z.object({
  paths: z.array(z.string()), message: z.string(), diff: z.string(), truncated: z.boolean(),
  warnings: z.array(z.string()), token: z.string(),
})

export const unifiedRemoteContribution = {
  package: 'dsh-plugin-workbench',
  descriptors: [
    {
      id: 'dsh-plugin-workbench#jobRadar/ping', service: 'jobRadar', namespace: 'jobRadar', method: 'ping',
      invocation: { kind: 'direct' }, parameters: [], result: strict('dsh-plugin-workbench#Ping', z.object({ ok: z.literal(true) })),
    },
    {
      id: 'dsh-plugin-workbench#jobRadar/list', service: 'jobRadar', namespace: 'jobRadar', method: 'list',
      invocation: { kind: 'direct' },
      parameters: [parameter('filter', z.object({ grade: z.string().optional(), status: z.string().optional(), days: z.number().optional() }))],
      result: strict('dsh-plugin-workbench#JobList', z.object({ jobs: z.array(job), total: z.number() })),
    },
    {
      id: 'dsh-plugin-workbench#jobRadar/stats', service: 'jobRadar', namespace: 'jobRadar', method: 'stats',
      invocation: { kind: 'direct' }, parameters: [], result: strict('dsh-plugin-workbench#JobStats', z.record(z.string(), z.number())),
    },
    {
      id: 'dsh-plugin-workbench#jobRadar/setStatus', service: 'jobRadar', namespace: 'jobRadar', method: 'setStatus',
      invocation: { kind: 'direct' },
      parameters: [parameter('jobId', z.string()), parameter('status', z.string())],
      result: strict('dsh-plugin-workbench#SetStatus', z.object({ ok: z.boolean(), error: z.string().optional() })),
    },
    {
      id: 'dsh-plugin-workbench#tablewareRadar/getAnalysis', service: 'tablewareRadar', namespace: 'tablewareRadar', method: 'getAnalysis',
      invocation: { kind: 'direct' }, parameters: [], result: strict('dsh-plugin-workbench#Analysis', z.union([analysis, z.null()])),
    },
    {
      id: 'dsh-plugin-workbench#tablewareRadar/getStatus', service: 'tablewareRadar', namespace: 'tablewareRadar', method: 'getStatus',
      invocation: { kind: 'direct' }, parameters: [],
      result: strict('dsh-plugin-workbench#AnalysisStatus', z.object({
        present: z.boolean(), path: z.string(), mtimeMs: z.number(), bytes: z.number(), generatedAt: z.union([z.string(), z.null()]),
      })),
    },
    {
      id: 'dsh-plugin-workbench#workbenchSync/refresh', service: 'workbenchSync', namespace: 'workbenchSync', method: 'refresh',
      invocation: { kind: 'direct' }, parameters: [], result: strict('dsh-plugin-workbench#SyncStatus', syncStatus),
    },
    {
      id: 'dsh-plugin-workbench#workbenchSync/preview', service: 'workbenchSync', namespace: 'workbenchSync', method: 'preview',
      invocation: { kind: 'direct' }, parameters: [], result: strict('dsh-plugin-workbench#SyncStatus', syncStatus),
    },
    {
      id: 'dsh-plugin-workbench#workbenchSync/commitPreview', service: 'workbenchSync', namespace: 'workbenchSync', method: 'commitPreview',
      invocation: { kind: 'direct' }, parameters: [parameter('paths', z.array(z.string())), parameter('message', z.string())],
      result: strict('dsh-plugin-workbench#CommitPreview', commitPreview),
    },
    {
      id: 'dsh-plugin-workbench#workbenchSync/commit', service: 'workbenchSync', namespace: 'workbenchSync', method: 'commit',
      invocation: { kind: 'direct' },
      parameters: [parameter('paths', z.array(z.string())), parameter('message', z.string()), parameter('previewToken', z.string())],
      result: strict('dsh-plugin-workbench#CommitResult', z.object({ commit: z.string(), status: syncStatus })),
    },
  ],
}
