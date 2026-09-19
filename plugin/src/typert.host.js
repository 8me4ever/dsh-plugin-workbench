/**
 * dsh-tableware-radar — host TYPERT manifest (hand-written, no generator).
 *
 * Auto-scanned and registered by `@deepseek-ai/dsh-typert-loader` from the package's
 * `./typert` export. Shape mirrors a `@deepseek-ai/dsh-typert-generator` product:
 * `TYPERT.invocations[].result` must be a strict codec `{mode:'strict', typeSymbol, schema}`.
 *
 * Deterministic order matters for reading; the two methods are the contract.
 */
import { METHODS } from './schemas.js'

const jsDoc_getAnalysis =
  '/**\n * 读取管道唯一真源 data/analysis.json。\n * @returns 分析结果;文件不存在时返回 null。\n * Read the pipeline\'s single source of truth data/analysis.json.\n * @returns The analysis, or null when the file is absent.\n */'
const jsDoc_getStatus =
  '/**\n * 探测 analysis.json 是否存在及其大小/修改时间。\n * @returns 状态对象(present/path/mtimeMs/bytes/generatedAt)。\n * Probe whether analysis.json exists and its size/mtime.\n * @returns A status object.\n */'

export const TYPERT = {
  package: 'dsh-tableware-radar',
  face: 'host',
  schemas: [],
  invocations: METHODS,
  model: {
    services: [
      {
        description:
          'dsh-tableware-radar 数据面服务(ctx.tablewareRadar):读取餐盘碗碟机会雷达的分析结果。'
          + ' Data-face service (ctx.tablewareRadar) exposing the tableware opportunity-radar analysis.',
        summary: 'dsh-tableware-radar 数据面服务 (dsh-tableware-radar data face)。',
        tags: [],
        jsDoc: '/** dsh-tableware-radar 数据面服务(ctx.tablewareRadar)。dsh-tableware-radar data face (ctx.tablewareRadar). */',
        key: 'tablewareRadar',
        exportName: 'TablewareRadarService',
        members: [
          {
            kind: 'method',
            name: 'getAnalysis',
            signature: 'getAnalysis(): Analysis | null',
            summary: '读取管道唯一真源 data/analysis.json。Read the pipeline\'s single source of truth data/analysis.json.',
            jsDoc: jsDoc_getAnalysis,
          },
          {
            kind: 'method',
            name: 'getStatus',
            signature: 'getStatus(): Status',
            summary: '探测 analysis.json 是否存在及其大小/修改时间。Probe whether analysis.json exists and its size/mtime.',
            jsDoc: jsDoc_getStatus,
          },
        ],
        types: [],
      },
    ],
    events: [],
    objects: [],
  },
}

export default TYPERT
