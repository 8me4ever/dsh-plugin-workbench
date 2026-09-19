/**
 * 工作台「项目」的接口契约 —— 这是你后续扩展工作台时唯一需要遵守的约定。
 *
 * 一个项目 = 工作台左侧导航里的一个标签页。工作台本身只负责：
 *   框架、导航、当前选中项、把上下文递给你。它对你的项目内容一无所知。
 *
 * 最小实现只有三个字段（id / title / render）：
 *
 * ```ts
 * import { createElement as h } from 'react'
 * import type { WorkbenchProject } from './types.ts'
 *
 * export const myProject: WorkbenchProject = {
 *   id: 'my-project',
 *   title: () => '我的项目',
 *   render: (ctx) => h('div', null, `共有 ${ctx.inventory.get().entries.length} 个插件`),
 * }
 * ```
 *
 * 写好后在 `slots.ts` 里替换掉对应的 `null` 即可，不需要改工作台本身。
 */
import type { ReactElement } from 'react'
import type { InventoryStore } from '../store.ts'

/**
 * 一条岗位记录 —— 只声明本项目真正用到的字段，其余字段原样忽略。
 *
 * 刻意写成"部分 + 可选"而不是照抄 job-radar 的完整 schema：岗位字段会
 * 随抓取源演进，工作台不该因为上游多了一个字段就编译不过。
 */
export interface JobRecord {
  readonly id: string | number
  readonly title?: string
  readonly company?: string
  readonly city?: string
  readonly salary_min?: number
  readonly salary_max?: number
  readonly experience_min?: number
  readonly experience_max?: number
  readonly education?: string
  readonly url?: string
  readonly source?: string
  readonly score?: number
  readonly grade?: string
  readonly status?: string
  readonly created_at?: string
  readonly updated_at?: string
  /** 评分明细，用来回答"这条为什么是 A 级"。 */
  readonly details?: {
    readonly skill?: number
    readonly experience?: number
    readonly company?: number
    readonly freshness?: number
    readonly commute?: number
    readonly other?: number
    readonly skill_hits?: readonly string[]
  }
}

/**
 * job-radar Remote 的客户端面（`remote.jobRadar`）。
 *
 * 由 `dsh-job-radar` 插件的宿主半部装载，所以它是本工作台之外的另一个包 ——
 * 也因此它是一个**可选**依赖，见下面 `ProjectContext.jobRadar`。
 */
export interface JobRadarFace {
  list(filter?: { grade?: string; status?: string; days?: number }): Promise<{
    jobs: readonly JobRecord[]
    total: number
  }>
  stats(): Promise<Record<string, number>>
  setStatus(id: string, status: string): Promise<{ ok: boolean; error?: string }>
}

/**
 * 机会雷达数据面的行结构 —— 与 `data/analysis.json` 的 schema 对齐
 * （见 dsh-tableware-radar 的 docs/ARCHITECTURE.md §3.2）。
 *
 * 同样写成"部分 + 可选"：分析字段会随管道演进，工作台不该因为上游多了一个
 * 字段就编译不过。项目只声明它真正渲染的字段。
 */
export interface TablewareAsinSample {
  asin?: string
  title?: string
  fetched?: number
  usable?: number
  rating_avg?: number
  ok?: boolean
}

/** `analysis.json.dimensions[]` 一行。 */
export interface TablewareDimension {
  id?: string
  name?: string
  definition?: string
  attention?: number
  net_sat?: number
  satisfaction?: number
  pos_share?: number
  neg_share?: number
  hits?: number
  asin_count?: number
  rankable?: boolean
  low_confidence?: boolean
}

/** `analysis.json.by_asin[]` 一行（③ 对比矩阵选列的输入）。 */
export interface TablewareByAsin {
  asin?: string
  title?: string
  rating_avg?: number
  opportunity?: number
  dimensions?: Record<string, { attention?: number; net_sat?: number; hits?: number }>
}

/** 一条证据。 */
export interface TablewareEvidence {
  quote?: string
  review_id?: string
  asin?: string
}

/** `analysis.json.opportunities[]` 一行。 */
export interface TablewareOpportunity {
  dimension?: string
  opportunity?: number
  attention?: number
  net_sat?: number
  hits?: number
  asin_count?: number
  top_evidence?: readonly TablewareEvidence[]
  supplier_action?: string
}

/** `analysis.json.selection_priority[]` 一行。 */
export interface TablewarePriority {
  dimension?: string
  opportunity?: number
  reason?: string
}

/** `analysis.json.risk_flags[]` 一行（SAF）。 */
export interface TablewareRiskFlag {
  dimension?: string
  value?: string
  polarity?: string
  hits?: number
  top_evidence?: readonly TablewareEvidence[]
}

/** `analysis.json.top_praise[]` / `top_complaint[]` 一行。 */
export interface TablewareShareRow {
  dimension?: string
  pos_share?: number
  neg_share?: number
  example_evidence?: string
}

/** `analysis.json.other_topics[]` 一行。 */
export interface TablewareTopic {
  topic_phrase?: string
  count?: number
}

/** `data_quality.sampling_bias`。 */
export interface TablewareSamplingBias {
  source?: string
  effects?: readonly string[]
  note?: string
}

/** `analysis.json.data_quality`。 */
export interface TablewareDataQuality {
  failed_asins?: readonly string[]
  underfilled_asins?: readonly { asin?: string; fetched?: number }[]
  low_confidence_dimensions?: readonly { id?: string; hits?: number; asin_count?: number; reason?: string }[]
  skipped_unusable?: number
  labeling_failures?: number
  sampling_bias?: TablewareSamplingBias
  gate?: string | null
}

/** `analysis.json.sample`。 */
export interface TablewareSample {
  asins?: readonly string[]
  comments_total?: number
  comments_usable?: number
  asins_with_data?: number
  labeled_coverage?: number
  date_range?: { from?: string; to?: string }
  per_asin?: readonly TablewareAsinSample[]
}

/** 离线管道的唯一真源 `data/analysis.json`（只读）。 */
export interface TablewareAnalysis {
  generated_at?: string
  dimension_set_version?: string
  sample?: TablewareSample
  dimensions?: readonly TablewareDimension[]
  by_asin?: readonly TablewareByAsin[]
  top_praise?: readonly TablewareShareRow[]
  top_complaint?: readonly TablewareShareRow[]
  opportunities?: readonly TablewareOpportunity[]
  selection_priority?: readonly TablewarePriority[]
  risk_flags?: readonly TablewareRiskFlag[]
  filters?: Record<string, number>
  other_topics?: readonly TablewareTopic[]
  data_quality?: TablewareDataQuality
}

/** `remote.tablewareRadar.getStatus()` 的返回结构。 */
export interface TablewareStatus {
  present: boolean
  path: string
  mtimeMs: number
  bytes: number
  generatedAt: string | null
}

/**
 * tableware-radar Remote 的客户端面（`remote.tablewareRadar`）。
 *
 * 由 `dsh-tableware-radar` 插件的宿主半部装载，所以它是本工作台之外的另一个
 * 包 —— 也因此它是一个**可选**依赖，见下面 `ProjectContext.tablewareRadar`。
 * 两个方法都是 **0 参数**（网关按描述符的 `parameters.length` 严格校验）。
 */
export interface TablewareRadarFace {
  getAnalysis(): Promise<TablewareAnalysis | null>
  getStatus(): Promise<TablewareStatus>
}

/**
 * 项目渲染时拿到的上下文 —— 由工作台注入，项目只读使用。
 *
 * 需要更多宿主能力时（其它 Remote、文件、网络），在 `src/client/index.ts`
 * 的 `apply()` 里把它加进这里一起传进来即可；只有那里才知道本插件
 * inject 了哪些服务。刻意不做成"把整个 cordis 上下文直接丢给项目"，
 * 否则每个项目都要自己处理服务未就绪的情况。
 */
export interface ProjectContext {
  /**
   * 绑定到本插件词条命名空间的翻译函数。
   * 项目自己的文案也可以直接用中文字面量 —— 那就不必走这里。
   */
  t: (key: string) => string
  /** 宿主插件清单的只读快照，附带 `refresh()` 可重新读取。 */
  inventory: InventoryStore
  /**
   * 解析 job-radar 数据面。**每次调用都要重新解析** —— 它由另一个插件的
   * 客户端半部异步挂载，早一次拿到 `undefined` 不代表之后也没有。
   *
   * 未装载时返回 `undefined`，项目据此渲染"数据源未装载"而不是抛错：
   * 一个项目不该因为它依赖的宿主插件缺席就把整块屏变成异常卡片。
   * 这也正是没有把 `remote.jobRadar` 写进 `inject` 的原因 —— 那是硬依赖，
   * 会让整个工作台一起停等一个可选插件。
   */
  jobRadar(): JobRadarFace | undefined
  /**
   * 解析 tableware-radar 数据面。**每次调用都要重新解析**，理由与 `jobRadar`
   * 完全一致：它由 `dsh-tableware-radar` 的客户端半部异步挂载。未装载时返回
   * `undefined`，项目渲染"数据面未装载"说明卡而不是抛错。同样刻意不写进 inject。
   */
  tablewareRadar(): TablewareRadarFace | undefined
}

/** 一个工作台项目。除 id 外全部可选字段都可以先不写。 */
export interface WorkbenchProject {
  /**
   * 稳定 id，同时是导航项的 key，也是 `onSelect` 传回来的值。
   * 建议 kebab-case，且不要用 `control-room`（那是内置控制室占用的）。
   */
  readonly id: string

  /** 导航项与页头显示的标题。返回字符串即可。 */
  title(): string

  /** 可选：标题下方的一句话说明，也用于控制室的项目位卡片。 */
  summary?(): string

  /** 可选：导航图标，返回一个 16×16 viewBox 的 `<svg>`。缺省时用中性方块。 */
  icon?(): ReactElement

  /**
   * 渲染项目主体。工作台已经提供了外层滚动容器与内边距，
   * 直接返回你这一屏的内容即可。
   * 返回 `null` 表示此刻没有内容可显示。
   */
  render(ctx: ProjectContext): ReactElement | null
}

/** 一个项目位：要么已被项目占用，要么还是空的（预留）。 */
export type ProjectSlot = WorkbenchProject | null
