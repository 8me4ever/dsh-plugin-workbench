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
