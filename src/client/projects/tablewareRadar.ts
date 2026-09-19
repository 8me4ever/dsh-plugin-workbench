/**
 * 项目 02 —— 餐盘碗碟机会雷达。
 *
 * 数据来自 `dsh-tableware-radar` 插件装载的 `tablewareRadar` 数据面，本项目
 * **不拥有**数据：它只读离线管道产出的唯一真源 `data/analysis.json` 快照。
 * 数据源是**可选**的：profile 没装该插件、或它还没挂载完成时，
 * `ctx.tablewareRadar()` 返回 undefined，这里渲染一张说明卡而不是抛错
 * （把 `remote.tablewareRadar` 写进 inject 会让整个工作台去停等一个可选插件）。
 *
 * 区块（对应 PRD §7.2 的 ①–⑧）：
 *   ① 概览数据   ② 维度机会榜   ◈ SAF 合规风险   ③ 品类对比矩阵
 *   ④ 选品优先级  ⑤ 好评亮点    ⑥ 差评聚焦       ⑦ 场景切片 & 其他话题
 *   ⑧ 数据完整性与采样偏差
 */
import { createElement as h, useEffect, useState, type ReactElement } from 'react'
import { CODE, HINT, OUTLINE_BUTTON, SECTION_TITLE, T } from '../tokens.ts'
import type {
  ProjectContext,
  TablewareAnalysis,
  TablewareByAsin,
  TablewareDimension,
  TablewareStatus,
  WorkbenchProject,
} from './types.ts'

/** 项目 id —— 导航 key，也是控制室项目位卡片上的标识。 */
export const TABLEWARE_RADAR_ID = 'tableware-radar'

/** 维度中文名回退（analysis.json 已带 name，这里仅当缺失时兜底）。 */
const DIM_NAME: Record<string, string> = {
  DUR: '耐用性', CLE: '易清洁', AES: '美观度', SIZ: '尺寸', PCK: '包装',
  SCN: '使用场景', STR: '强度/结构', HAN: '手感/握持', VAL: '性价比/安全', SAF: '合规/安全',
}

/** 场景切片的英文键 → 中文标签。 */
const SCN_LABEL: Record<string, string> = {
  everyday_dining: '日常就餐', entertaining: '宴客', afternoon_tea: '下午茶',
  roast_dinner: '烤肉晚餐', gifting: '送礼', kids_family: '亲子', baking_serving: '烘焙/盛放',
}

/**
 * ③ 对比矩阵默认列数。
 *
 * 对齐 pipeline `config.MATRIX_TOP_ASINS`（默认 5，允许 5–8）。客户端读不到
 * Python 配置，故在此镜像默认值；「展开全部」时列数不受该上限约束。
 */
const MATRIX_TOP_ASINS = 5

/** 不入矩阵的行维度：SCN 只作筛选、SAF 单列风险（PRD §4.4），OTHER 为逃生口。 */
const MATRIX_EXCLUDED_IDS: ReadonlySet<string> = new Set(['SCN', 'SAF', 'OTHER'])

/**
 * ③ 选列口径披露（PRD §7.4）—— 与 ⑧ 的采样偏差披露同一层级的小字。
 *
 * 用词刻意固定：矩阵列是按商品机会暴露挑选的，**不代表**该商品的综合评价，
 * 否则读者会把「列少」误当成「这个商品没问题」。
 */
const MATRIX_DISCLOSURE =
  '当前展示的 5–8 列是按 asin_opportunity 选取的，不代表该商品的综合评价'

/** 一次读取的结果。 */
interface LoadState {
  status: 'idle' | 'loading' | 'ready' | 'missing' | 'error' | 'not-generated'
  analysis: TablewareAnalysis | null
  probe: TablewareStatus | null
  readAt: number
  error: string
}

export const tablewareRadarProject: WorkbenchProject = {
  id: TABLEWARE_RADAR_ID,
  title: () => '餐盘碗碟机会雷达',
  summary: () => '读 analysis.json —— 维度机会榜、选品优先级与数据完整性',
  icon: () => dishGlyph(),
  render: (ctx) => h(TablewareRadarView, { ctx }),
}

/**
 * The project body. Exported so the headless smoke test can render it directly
 * with a stub context (the same treatment `jobRadar.ts` gets).
 */
export function TablewareRadarView(props: { ctx: ProjectContext }): ReactElement {
  const { ctx } = props
  const [load, setLoad] = useState<LoadState>({
    status: 'idle', analysis: null, probe: null, readAt: 0, error: '',
  })
  const [nonce, setNonce] = useState(0)
  // ③ matrix column expansion lives here (not in the section), so the toggle is
  // a plain prop and the section stays a pure function of its inputs — the
  // headless smoke test renders `TablewareRadarView` directly and would never
  // see a section component's output.
  const [matrixExpanded, setMatrixExpanded] = useState(false)

  useEffect(() => {
    let live = true
    // Resolved per read, never cached: the data face mounts asynchronously.
    const face = ctx.tablewareRadar()
    if (face === undefined) {
      setLoad({ status: 'missing', analysis: null, probe: null, readAt: 0, error: '' })
      return () => { live = false }
    }
    setLoad((prev) => ({ ...prev, status: 'loading' }))
    void (async () => {
      try {
        const probe = await face.getStatus()
        if (!live) return
        if (!probe.present) {
          setLoad({ status: 'not-generated', analysis: null, probe, readAt: Date.now(), error: '' })
          return
        }
        const analysis = await face.getAnalysis()
        if (!live) return
        if (analysis === null) {
          setLoad({ status: 'not-generated', analysis: null, probe, readAt: Date.now(), error: '' })
          return
        }
        setLoad({ status: 'ready', analysis, probe, readAt: Date.now(), error: '' })
      } catch (err: unknown) {
        if (live) setLoad({ status: 'error', analysis: null, probe: null, readAt: 0, error: message(err) })
      }
    })()
    return () => { live = false }
  }, [nonce])

  const refresh = (): void => setNonce((n) => n + 1)

  if (load.status === 'missing') return sourceMissing()
  if (load.status === 'error') return sourceError(load.error, refresh)
  if (load.status === 'not-generated') return notGenerated(load.probe, refresh)
  if (load.status !== 'ready' || load.analysis === null) return loading()
  return body(load.analysis, load, refresh, matrixExpanded, () => setMatrixExpanded((v) => !v))
}

// ---- the ready body -------------------------------------------------------

function body(
  a: TablewareAnalysis,
  load: LoadState,
  onRefresh: () => void,
  matrixExpanded: boolean,
  onToggleMatrix: () => void,
): ReactElement {
  return h(
    'div',
    { 'data-tableware': 'ready', style: { display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 980 } },
    overview(a, load, onRefresh),                        // ①
    opportunities(a),                                     // ②
    riskFlags(a),                                         // ◈ SAF
    comparisonMatrix(a, matrixExpanded, onToggleMatrix),  // ③
    selectionPriority(a),                                 // ④
    shares(a),                                            // ⑤ ⑥
    scenarios(a),                                         // ⑦
    dataQuality(a),                                       // ⑧
  )
}

// ---- ① 概览 ---------------------------------------------------------------

function overview(a: TablewareAnalysis, load: LoadState, onRefresh: () => void): ReactElement {
  const s = a.sample ?? {}
  const coverage = typeof s.labeled_coverage === 'number'
    ? `${Math.round(s.labeled_coverage * 100)}%`
    : '-'
  const cells: [string, string][] = [
    ['商品数', str(s.asins_with_data)],
    ['可用评论', str(s.comments_usable)],
    ['评论总数', str(s.comments_total)],
    ['打标覆盖率', coverage],
    ['时间范围', rangeText(s.date_range)],
    ['维度版本', a.dimension_set_version ?? '-'],
  ]
  return h(
    'section',
    { 'data-block': '1' },
    headerRow('① 概览', 'remote.tablewareRadar', load, onRefresh),
    h(
      'div',
      { style: { display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 8, marginTop: 12 } },
      ...cells.map(([label, value]) => h(
        'div',
        { key: label, style: statCardStyle() },
        h('div', { style: { fontSize: 11, color: T.text3 } }, label),
        h('div', { style: { fontSize: 18, fontWeight: 500, lineHeight: 1.5, color: T.text1 } }, value),
      )),
    ),
    h(
      'div',
      { style: { ...HINT, marginTop: 8 } },
      a.generated_at
        ? `数据快照生成于 ${a.generated_at}。这是离线管道的导出时间，不是抓取时间 —— 数字停住说明该重跑一次管道了。`
        : '快照缺少 generated_at。',
    ),
  )
}

// ---- ② 维度机会榜 ---------------------------------------------------------

function opportunities(a: TablewareAnalysis): ReactElement {
  const dims = new Map<string, TablewareDimension>()
  for (const d of a.dimensions ?? []) if (d.id) dims.set(d.id, d)
  const opps = [...(a.opportunities ?? [])].sort((x, y) => (y.opportunity ?? 0) - (x.opportunity ?? 0))

  return h(
    'section',
    { 'data-block': '2', style: sectionGap() },
    h('div', { style: SECTION_TITLE }, '② 维度机会榜（仅 rankable 维度）'),
    opps.length === 0
      ? emptyNote('没有 rankable 维度 —— 样本太小，先扩商品数或补维度。')
      : h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', marginTop: 6 } },
        ...opps.map((o) => {
          const name = dims.get(o.dimension ?? '')?.name ?? DIM_NAME[o.dimension ?? ''] ?? o.dimension ?? '-'
          return h(
            'div',
            { key: o.dimension, 'data-opp': o.dimension, style: rowStyle() },
            h(
              'div',
              { style: { display: 'flex', alignItems: 'baseline', gap: 8 } },
              h('span', { style: { fontSize: 13.5, fontWeight: 500, color: T.text1 } }, `${name}（${o.dimension}）`),
              h('span', { style: { ...CODE, color: T.brand, marginLeft: 'auto' } }, `机会分 ${fmt(o.opportunity)}`),
            ),
            h(
              'div',
              { style: { ...HINT, marginTop: 2 } },
              `提及率 ${fmt(o.attention)} · 净满意度 ${fmt(o.net_sat)} · 命中 ${str(o.hits)} · 覆盖 ${str(o.asin_count)} 个商品`,
            ),
            o.supplier_action
              ? h('div', { style: { ...HINT, marginTop: 4, color: T.text2 } }, `供给动作：${o.supplier_action}`)
              : null,
            evidenceList(o.top_evidence),
          )
        }),
      ),
    lowConfidenceNote(a),
  )
}

/** 把被 rankable 过滤掉的维度显式列出来（避免「没上榜=不存在」的误解）。 */
function lowConfidenceNote(a: TablewareAnalysis): ReactElement | null {
  const rows = (a.dimensions ?? []).filter((d) => d.low_confidence === true)
  if (rows.length === 0) return null
  return h(
    'div',
    { style: { ...HINT, marginTop: 8 } },
    `未达 rankable 而暂不上榜的维度：${rows.map((d) => `${d.name ?? d.id}（命中 ${str(d.hits)}）`).join('、')}。它们仍作为 ③ 对比矩阵的行列出（降透明度并标「n不足」），只是不参与机会分排序。`,
  )
}

// ---- ◈ SAF 合规风险 --------------------------------------------------------

function riskFlags(a: TablewareAnalysis): ReactElement | null {
  const flags = a.risk_flags ?? []
  if (flags.length === 0) return null
  return h(
    'section',
    { 'data-block': 'SAF', style: sectionGap() },
    h('div', { style: { ...SECTION_TITLE, color: T.danger } }, '◈ SAF 合规/安全风险（单列，不入机会分）'),
    ...flags.map((f) => h(
      'div',
      { key: `${f.value}`, style: { ...rowStyle(), borderLeft: `3px solid ${T.danger}`, paddingLeft: 10 } },
      h('div', { style: { fontSize: 13, color: T.text1 } }, `${f.value ?? '-'} · 命中 ${str(f.hits)}`),
      evidenceList(f.top_evidence),
    )),
  )
}

// ---- ③ 品类对比矩阵 -------------------------------------------------------
//
// 列 = `by_asin[].opportunity`（口径 **asin_opportunity**）降序 Top
// `MATRIX_TOP_ASINS`（默认 5），列数超过默认时给一个「展开全部 N 个 ASIN」入口；
// **增列只影响列、绝不改变行序**（行集合只由 `dimensions[]` 决定）。
//
// 行 = 评分维度（排除 SCN/SAF/OTHER）：rankable 维度按**机会分降序**在上；
// `low_confidence`（≡ !rankable）维度照常列出以回答「为什么它没上榜」，
// 但**降透明度**并挂「n不足」角标，且不参与机会分排序。
//
// 单元格 = `关注度 / 净满意`（该商品在该维度上的局部 attention / net_sat）。
// 表头上方固定一行**选列口径披露**（PRD §7.4），与 ⑧ 的采样偏差披露同层级。

function comparisonMatrix(
  a: TablewareAnalysis,
  expanded: boolean,
  onToggle: () => void,
): ReactElement {
  const cols = [...(a.by_asin ?? [])]
    .filter((r) => (r.asin ?? '') !== '')
    .sort((x, y) =>
      (y.opportunity ?? Number.NEGATIVE_INFINITY) - (x.opportunity ?? Number.NEGATIVE_INFINITY)
      || cmpStr(x.asin ?? '', y.asin ?? ''))

  const oppByDim = new Map<string, number>()
  for (const o of a.opportunities ?? []) if (o.dimension) oppByDim.set(o.dimension, o.opportunity ?? 0)

  const scoring = (a.dimensions ?? []).filter((d) => d.id !== undefined && !MATRIX_EXCLUDED_IDS.has(d.id))
  const rankable = scoring
    .filter((d) => d.rankable === true)
    .sort((x, y) => (oppByDim.get(y.id ?? '') ?? 0) - (oppByDim.get(x.id ?? '') ?? 0)
      || cmpStr(x.id ?? '', y.id ?? ''))
  const lowConf = scoring
    .filter((d) => d.rankable !== true)
    .sort((x, y) => (y.hits ?? 0) - (x.hits ?? 0) || cmpStr(x.id ?? '', y.id ?? ''))
  const rows = [...rankable, ...lowConf]

  const collapsible = cols.length > MATRIX_TOP_ASINS
  const shown = expanded || !collapsible ? cols : cols.slice(0, MATRIX_TOP_ASINS)

  return h(
    'section',
    { 'data-block': '3', style: sectionGap() },
    h('div', { style: SECTION_TITLE }, '③ 品类对比矩阵'),
    // 选列口径披露 —— 与 ⑧ 的采样偏差披露同款「小字框」，保证同样是「必读声明」
    // 而非行内提示（PRD §7.4）。
    h(
      'div',
      {
        'data-matrix-disclosure': 'yes',
        style: {
          marginTop: 6, padding: '6px 10px', borderRadius: 8,
          border: `1px solid ${T.border2}`, background: T.bgLayer1,
        },
      },
      h('div', { style: { ...HINT, color: T.text2 } }, MATRIX_DISCLOSURE),
    ),
    cols.length === 0
      ? emptyNote('没有可对比的商品（by_asin 为空）。')
      : rows.length === 0
        ? emptyNote('没有可对比的评分维度。')
        : matrixTable(shown, rows, oppByDim),
    collapsible
      ? h(
        'button',
        {
          type: 'button',
          'data-matrix-expand': expanded ? 'collapse' : 'expand',
          onClick: onToggle,
          style: { ...OUTLINE_BUTTON, marginTop: 6, alignSelf: 'flex-start' },
        },
        expanded ? '收起，只看 Top 5' : `展开全部 ${cols.length} 个 ASIN`,
      )
      : null,
  )
}

function matrixTable(
  cols: readonly TablewareByAsin[],
  rows: readonly TablewareDimension[],
  oppByDim: Map<string, number>,
): ReactElement {
  const grid = `minmax(132px, 1.5fr) repeat(${cols.length}, minmax(88px, 1fr))`
  return h(
    'div',
    { 'data-matrix': 'yes', style: { display: 'flex', flexDirection: 'column', marginTop: 6 } },
    h(
      'div',
      {
        style: {
          display: 'grid', gridTemplateColumns: grid, columnGap: 8, alignItems: 'end',
          paddingBottom: 6, borderBottom: `1px solid ${T.border2}`,
        },
      },
      h('div', { style: { ...SECTION_TITLE, textTransform: 'none' } }, `维度 \\ 商品（${cols.length} 列）`),
      ...cols.map((c) => h(
        'div',
        { key: c.asin, 'data-matrix-col': c.asin, style: { minWidth: 0 } },
        h('div', { style: { ...CODE, color: T.text1, fontWeight: 500 } }, c.asin ?? '-'),
        h(
          'div',
          { style: { ...HINT, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
          c.title && c.title !== '' ? c.title : '（无标题）',
        ),
        h(
          'div',
          { style: { ...HINT, marginTop: 2 } },
          `${typeof c.rating_avg === 'number' && c.rating_avg > 0 ? `★${fmt(c.rating_avg)} · ` : ''}机会暴露 ${fmt(c.opportunity)}`,
        ),
      )),
    ),
    ...rows.map((d) => matrixRow(d, cols, grid, oppByDim)),
  )
}

function matrixRow(
  d: TablewareDimension,
  cols: readonly TablewareByAsin[],
  grid: string,
  oppByDim: Map<string, number>,
): ReactElement {
  const dimId = d.id ?? ''
  const low = d.rankable !== true
  const name = d.name || DIM_NAME[dimId] || dimId || '-'
  return h(
    'div',
    {
      key: dimId,
      'data-matrix-row': dimId,
      'data-matrix-low': low ? 'yes' : 'no',
      style: {
        display: 'grid', gridTemplateColumns: grid, columnGap: 8, alignItems: 'center',
        padding: '7px 0', borderBottom: `1px solid ${T.border1}`,
        opacity: low ? 0.5 : 1,
      },
    },
    h(
      'div',
      { style: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 } },
      h('span', { style: { fontSize: 12.5, color: T.text1 } }, `${name}（${dimId}）`),
      low
        ? h(
          'span',
          {
            style: {
              fontSize: 10.5, color: T.warn, border: `1px solid ${T.border2}`,
              borderRadius: 4, padding: '0 4px', flex: '0 0 auto',
            },
          },
          'n不足',
        )
        : h('span', { style: { ...HINT, marginLeft: 'auto' } }, `机会分 ${fmt(oppByDim.get(dimId))}`),
    ),
    ...cols.map((c) => h(
      'div',
      { key: `${dimId}-${c.asin}`, style: { ...CODE, color: low ? T.text3 : T.text2 } },
      matrixCell(c, dimId),
    )),
  )
}

/** 单元格文本：`关注度 / 净满意`；该商品在该维度无命中时留空占位。 */
function matrixCell(row: TablewareByAsin, dimId: string): string {
  const cell = row.dimensions?.[dimId]
  if (!cell) return '—'
  return `${fmt(cell.attention)} / ${fmt(cell.net_sat)}`
}

function cmpStr(x: string, y: string): number {
  return x < y ? -1 : x > y ? 1 : 0
}

// ---- ④ 选品优先级 ---------------------------------------------------------

function selectionPriority(a: TablewareAnalysis): ReactElement {
  const rows = a.selection_priority ?? []
  const dims = new Map<string, TablewareDimension>()
  for (const d of a.dimensions ?? []) if (d.id) dims.set(d.id, d)
  return h(
    'section',
    { 'data-block': '4', style: sectionGap() },
    h('div', { style: SECTION_TITLE }, `④ 选品优先级（前 ${rows.length} 项，≤7）`),
    rows.length === 0
      ? emptyNote('暂无优先级项。')
      : h(
        'ol',
        { style: { margin: '6px 0 0', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 4 } },
        ...rows.map((r) => h(
          'li',
          { key: r.dimension, style: { fontSize: 12.5, color: T.text2 } },
          h('span', { style: { color: T.text1, fontWeight: 500 } },
            `${dims.get(r.dimension ?? '')?.name ?? DIM_NAME[r.dimension ?? ''] ?? r.dimension} · 机会分 ${fmt(r.opportunity)}`),
          r.reason ? h('span', { style: { color: T.text3 } }, ` — ${r.reason}`) : null,
        )),
      ),
  )
}

// ---- ⑤ 好评亮点 / ⑥ 差评聚焦 ----------------------------------------------

function shares(a: TablewareAnalysis): ReactElement {
  const dims = new Map<string, TablewareDimension>()
  for (const d of a.dimensions ?? []) if (d.id) dims.set(d.id, d)
  const nameOf = (id?: string): string => dims.get(id ?? '')?.name ?? DIM_NAME[id ?? ''] ?? id ?? '-'
  return h(
    'section',
    { style: sectionGap() },
    h(
      'div',
      { 'data-block': '5', style: sectionGap() },
      h('div', { style: SECTION_TITLE }, '⑤ 好评亮点'),
      shareRows(a.top_praise, 'pos', nameOf),
    ),
    h(
      'div',
      { 'data-block': '6', style: sectionGap() },
      h('div', { style: SECTION_TITLE }, '⑥ 差评聚焦'),
      shareRows(a.top_complaint, 'neg', nameOf),
    ),
  )
}

function shareRows(
  rows: readonly { dimension?: string; pos_share?: number; neg_share?: number; example_evidence?: string }[] | undefined,
  which: 'pos' | 'neg',
  nameOf: (id?: string) => string,
): ReactElement {
  const list = rows ?? []
  if (list.length === 0) return emptyNote('暂无数据。')
  return h(
    'div',
    { style: { display: 'flex', flexDirection: 'column', marginTop: 4 } },
    ...list.map((r) => {
      const share = which === 'pos' ? r.pos_share : r.neg_share
      return h(
        'div',
        { key: r.dimension, style: rowStyle() },
        h('div', { style: { fontSize: 13, color: T.text1 } },
          `${nameOf(r.dimension)} · 占比 ${fmt(share)}`),
        r.example_evidence
          ? h('div', { style: { ...HINT, fontStyle: 'italic', marginTop: 2 } }, `“${r.example_evidence}”`)
          : null,
      )
    }),
  )
}

// ---- ⑦ 场景切片 & 其他话题 ------------------------------------------------

function scenarios(a: TablewareAnalysis): ReactElement {
  const filters = a.filters ?? {}
  const entries = Object.entries(filters)
  const max = entries.reduce((m, [, v]) => Math.max(m, typeof v === 'number' ? v : 0), 0)
  return h(
    'section',
    { 'data-block': '7', style: sectionGap() },
    h('div', { style: SECTION_TITLE }, '⑦ 场景切片 & 其他话题（SCN 仅作筛选，不入机会分）'),
    entries.length === 0
      ? emptyNote('无场景切片。')
      : h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 } },
        ...entries.map(([key, value]) => {
          const count = typeof value === 'number' ? value : 0
          const width = max > 0 ? Math.round((count / max) * 100) : 0
          return h(
            'div',
            { key, style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 } },
            h('span', { style: { width: 84, color: T.text2, flex: '0 0 auto' } }, SCN_LABEL[key] ?? key),
            h(
              'span',
              { style: { flex: '1 1 auto', height: 6, borderRadius: 3, background: T.bgLayer2, overflow: 'hidden' } },
              h('span', { style: { display: 'block', height: '100%', width: `${width}%`, background: T.info, borderRadius: 3 } }),
            ),
            h('span', { style: { width: 32, textAlign: 'right', color: T.text3, flex: '0 0 auto' } }, String(count)),
          )
        }),
      ),
    (a.other_topics ?? []).length > 0
      ? h(
        'div',
        { style: { marginTop: 10 } },
        h('div', { style: { ...SECTION_TITLE, marginBottom: 4 } }, '其他话题（下一轮阶段 A 输入）'),
        h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 6 } },
          ...(a.other_topics ?? []).map((tp) => h(
            'span',
            { key: tp.topic_phrase, style: { fontSize: 11.5, color: T.text2, background: T.bgLayer2, borderRadius: 4, padding: '2px 7px' } },
            `${tp.topic_phrase} · ${str(tp.count)}`,
          )),
        ),
      )
      : null,
  )
}

// ---- ⑧ 数据完整性与采样偏差 ----------------------------------------------

function dataQuality(a: TablewareAnalysis): ReactElement {
  const q = a.data_quality ?? {}
  const bias = q.sampling_bias
  const lowConf = q.low_confidence_dimensions ?? []
  return h(
    'section',
    { 'data-block': '8', style: sectionGap() },
    h('div', { style: SECTION_TITLE }, '⑧ 数据完整性与采样偏差'),
    q.gate
      ? h('div', { style: { ...HINT, marginTop: 4, color: T.warn } }, `阶段闸门已触发：${q.gate} —— 结果不完整，需回到阶段 B 修正后重跑。`)
      : null,
    h(
      'div',
      { style: { ...HINT, marginTop: 6 } },
      `未能打标条数 ${str(q.labeling_failures)} · 因不可用跳过 ${str(q.skipped_unusable)}`,
    ),
    (q.failed_asins ?? []).length > 0
      ? h('div', { style: { ...HINT, marginTop: 2 } }, `抓取失败的 ASIN：${(q.failed_asins ?? []).join('、')}`)
      : null,
    (q.underfilled_asins ?? []).length > 0
      ? h('div', { style: { ...HINT, marginTop: 2 } },
        `未达标 ASIN：${(q.underfilled_asins ?? []).map((u) => `${u.asin}（${str(u.fetched)} 条）`).join('、')}`)
      : null,
    lowConf.length > 0
      ? h('div', { style: { ...HINT, marginTop: 2 } },
        `低置信维度：${lowConf.map((d) => `${d.id}（${d.reason ?? '?'}）`).join('、')}`)
      : null,
    bias
      ? h(
        'div',
        { 'data-sampling-bias': 'yes', style: { marginTop: 8, padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border2}`, background: T.bgLayer1 } },
        h('div', { style: { fontSize: 12, color: T.text2 } }, `采样偏差来源：${bias.source ?? '-'}`),
        h('div', { style: { ...HINT, marginTop: 4 } }, bias.note ?? ''),
        (bias.effects ?? []).length > 0
          ? h('div', { style: { ...HINT, marginTop: 2, color: T.textDim } },
            `偏差方向：${(bias.effects ?? []).map((e) => biasEffectLabel(e)).join('、')}`)
          : null,
      )
      : null,
  )
}

function biasEffectLabel(effect: string): string {
  if (effect === 'complaint_dims_overestimated') return '抱怨类维度高估'
  if (effect === 'casual_mention_dims_underestimated') return '随口一提的维度低估'
  return effect
}

// ---- 三种非就绪状态 -------------------------------------------------------

function loading(): ReactElement {
  return h('div', { 'data-tableware': 'loading', style: { ...HINT, padding: '16px 0' } }, '正在读取 analysis.json…')
}

/** 数据面未装载：说清楚是什么、为什么、怎么办。 */
function sourceMissing(): ReactElement {
  return h(
    'div',
    {
      'data-tableware': 'missing',
      style: {
        maxWidth: 620, margin: '16px auto 0', padding: '18px 20px',
        border: `1px dashed ${T.border2}`, borderRadius: 12, background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.text1 } }, '机会雷达数据面未装载'),
    h('div', { style: { ...HINT, marginTop: 8 } },
      '这个项目自己不读文件 —— 分析结果由 dsh-tableware-radar 插件通过 remote.tablewareRadar 提供。当前 profile 里没有解析到这个数据面，所以这里先空着。'),
    h('div', { style: { ...HINT, marginTop: 8 } }, '把该插件装进同一个 profile，然后重启宿主：'),
    codeBlock('dsh plugin --profile <profile> add "file:F:/Samuel/dsh-plugins/dsh-tableware-radar/plugin"'),
    h('div', { style: { ...HINT, marginTop: 8, color: T.textDim } },
      '注意：这个依赖是刻意做成可选的 —— 工作台的其余部分在它缺席时照常工作。'),
  )
}

/** 数据面在、但调用出错。 */
function sourceError(error: string, onRetry: () => void): ReactElement {
  return h(
    'div',
    {
      'data-tableware': 'error',
      style: {
        maxWidth: 620, margin: '16px auto 0', padding: '14px 16px',
        border: `1px solid ${T.border2}`, borderLeft: `3px solid ${T.danger}`,
        borderRadius: 10, background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.danger } }, '读取分析结果失败'),
    h('div', { style: { ...CODE, marginTop: 6, color: T.text2, wordBreak: 'break-word' } }, error),
    h('button', { type: 'button', onClick: onRetry, style: { ...OUTLINE_BUTTON, marginTop: 10 } }, '重试'),
  )
}

/** 数据面在、但还没跑过流水线（analysis.json 不存在）。 */
function notGenerated(probe: TablewareStatus | null, onRefresh: () => void): ReactElement {
  return h(
    'div',
    {
      'data-tableware': 'not-generated',
      style: {
        maxWidth: 620, margin: '16px auto 0', padding: '18px 20px',
        border: `1px dashed ${T.border2}`, borderRadius: 12, background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.text1 } }, '尚未跑过流水线'),
    h('div', { style: { ...HINT, marginTop: 8 } },
      '数据面已装载，但还没有找到分析结果文件。跑一次离线管道即可生成：'),
    codeBlock('python -m tableware_radar.cli run --all'),
    probe?.path
      ? h('div', { style: { ...HINT, marginTop: 8, color: T.textDim } }, `期望路径：${probe.path}`)
      : null,
    h('button', { type: 'button', onClick: onRefresh, style: { ...OUTLINE_BUTTON, marginTop: 10 } }, '我已生成，刷新'),
  )
}

// ---- helpers --------------------------------------------------------------

function headerRow(
  title: string,
  source: string,
  load: LoadState,
  onRefresh: () => void,
): ReactElement {
  return h(
    'div',
    { style: { display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 6, borderBottom: `1px solid ${T.border1}` } },
    h('span', { style: { ...SECTION_TITLE, flex: '1 1 auto' } }, title),
    h('span', { style: { ...CODE, color: T.textDim } }, source),
    h('span', { style: HINT, 'data-read-at': String(load.readAt) },
      load.status === 'loading' && load.readAt === 0
        ? '正在读取…'
        : `读取于 ${new Date(load.readAt).toLocaleTimeString()}`),
    h('button', { type: 'button', onClick: onRefresh, style: OUTLINE_BUTTON }, '刷新'),
  )
}

function evidenceList(rows: readonly { quote?: string; review_id?: string; asin?: string }[] | undefined): ReactElement | null {
  const list = (rows ?? []).filter((r) => r.quote)
  if (list.length === 0) return null
  return h(
    'div',
    { style: { display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 } },
    ...list.slice(0, 3).map((r, i) => h(
      'div',
      { key: `${r.review_id ?? 'q'}-${i}`, style: { ...HINT, fontStyle: 'italic', color: T.text3 } },
      `“${r.quote}”${r.asin ? ` — ${r.asin}` : ''}`,
    )),
  )
}

function emptyNote(text: string): ReactElement {
  return h('div', { style: { ...HINT, padding: '8px 0' } }, text)
}

function codeBlock(text: string): ReactElement {
  return h(
    'div',
    {
      style: {
        ...CODE, marginTop: 8, padding: '8px 10px', borderRadius: 8,
        background: T.bgLayer2, border: `1px solid ${T.border1}`, wordBreak: 'break-all',
      },
    },
    text,
  )
}

function sectionGap(): { display: string; flexDirection: string; gap: number } {
  return { display: 'flex', flexDirection: 'column', gap: 4 }
}

function rowStyle(): Record<string, string | number> {
  return { padding: '8px 0', borderBottom: `1px solid ${T.border1}` }
}

function statCardStyle(): Record<string, string | number> {
  return { padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border1}`, background: T.bgLayer1 }
}

/** Glyph for the project: a plate seen from above. */
function dishGlyph(): ReactElement {
  return h(
    'svg',
    {
      width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none',
      stroke: 'currentColor', strokeWidth: 1.3, 'aria-hidden': true, style: { flex: '0 0 auto' },
    },
    h('circle', { cx: 8, cy: 8, r: 6.2 }),
    h('circle', { cx: 8, cy: 8, r: 3.4 }),
    h('circle', { cx: 8, cy: 8, r: 0.8, fill: 'currentColor', stroke: 'none' }),
  )
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function str(value: unknown): string {
  return value === undefined || value === null || value === '' ? '-' : String(value)
}

function fmt(value: unknown): string {
  return typeof value === 'number' ? String(Math.round(value * 1000) / 1000) : '-'
}

function rangeText(range: { from?: string; to?: string } | undefined): string {
  if (!range || (!range.from && !range.to)) return '-'
  return `${range.from || '?'} ~ ${range.to || '?'}`
}
