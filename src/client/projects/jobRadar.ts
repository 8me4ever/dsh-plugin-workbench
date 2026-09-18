/**
 * 项目 01 —— Job Radar 岗位看板。
 *
 * 数据来自 `dsh-job-radar` 插件装载的 `jobRadar` Remote，本项目**不拥有**
 * 数据：它只读快照、并通过同一个 Remote 写回状态。所以工作台里的这块屏和
 * 插件自带的 Job Radar 设置页看到的是同一份数据、走同一条写入路径 ——
 * 没有第二份 jobs.json 读取实现，也就没有第二个可能跟它不一致的地方。
 *
 * 数据源是**可选**的。profile 没装 dsh-job-radar、或者它还没挂载完成时，
 * `ctx.jobRadar()` 返回 undefined，这里渲染一张说明卡。见 types.ts 里
 * `ProjectContext.jobRadar` 的注释：把 `remote.jobRadar` 写进 inject 会让
 * 整个工作台去停等一个可选插件，那是错的。
 *
 * 状态放在组件里而不是共享 store：这份数据只有这一屏要看，且切换导航时
 * 重新挂载、重新读一次快照正是想要的行为。
 */
import { createElement as h, useEffect, useState, type ReactElement } from 'react'
import { CODE, HINT, OUTLINE_BUTTON, SECTION_TITLE, T } from '../tokens.ts'
import type { JobRadarFace, JobRecord, ProjectContext, WorkbenchProject } from './types.ts'

/** 项目 id —— 导航 key，也是控制室项目位卡片上的标识。 */
export const JOB_RADAR_ID = 'job-radar'

/** 一屏先渲染多少条。146 条全铺出来没人看得下去，剩下的按需展开。 */
const PAGE = 25

const GRADES = ['S', 'A', 'B', 'C']
const STATUSES = ['new', 'applied', 'interested', 'rejected']
const STATUS_LABEL: Record<string, string> = {
  new: '新发现',
  applied: '已投递',
  interested: '有意向',
  rejected: '已放弃',
}

/** 等级色：用工作台令牌，浅深主题都不会跑偏。 */
function gradeColor(grade?: string): string {
  switch (grade) {
    case 'S': return T.ok
    case 'A': return T.brand
    case 'B': return T.warn
    case 'C': return T.text3
    default: return T.textDim
  }
}

/** 状态色，和上面同一套来源。 */
function statusColor(status?: string): string {
  switch (status) {
    case 'applied': return T.ok
    case 'interested': return T.warn
    case 'rejected': return T.textDim
    default: return T.info
  }
}

/** 读一次快照的结果。 */
interface LoadState {
  status: 'idle' | 'loading' | 'ready' | 'missing' | 'error'
  jobs: readonly JobRecord[]
  /** Epoch ms of the successful read, or 0. */
  readAt: number
  error: string
}

export const jobRadarProject: WorkbenchProject = {
  id: JOB_RADAR_ID,
  title: () => 'Job Radar',
  summary: () => '岗位看板 · 读 job-radar 快照，可直接标记状态',
  icon: () => radarGlyph(),
  // `render` 由工作台直接调用，不能自己持有 hook 状态；所以它只把上下文
  // 交给一个真正的组件去渲染。
  render: (ctx) => h(JobRadarView, { ctx }),
}

/**
 * The project body. Exported so the headless smoke test can render it directly
 * with a stub context — the same treatment the control room gets.
 */
export function JobRadarView(props: { ctx: ProjectContext }): ReactElement {
  const { ctx } = props
  const [load, setLoad] = useState<LoadState>({ status: 'idle', jobs: [], readAt: 0, error: '' })
  const [gradeFilter, setGradeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [shown, setShown] = useState(PAGE)
  const [pending, setPending] = useState('')
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let live = true
    // Resolved per read, never cached: the other plugin mounts asynchronously.
    const face = ctx.jobRadar()
    if (face === undefined) {
      setLoad({ status: 'missing', jobs: [], readAt: 0, error: '' })
      return () => { live = false }
    }
    setLoad((prev) => ({ ...prev, status: 'loading' }))
    face.list()
      .then((res) => {
        if (!live) return
        setLoad({ status: 'ready', jobs: res?.jobs ?? [], readAt: Date.now(), error: '' })
      })
      .catch((err: unknown) => {
        if (live) setLoad({ status: 'error', jobs: [], readAt: 0, error: message(err) })
      })
    return () => { live = false }
  }, [nonce])

  const jobs = load.jobs
  const gradeCount = tally(jobs, (j) => j.grade)
  const statusCount = tally(jobs, (j) => j.status)
  // 一次取全量、在本地筛选：等级/状态的切换是零延迟的，计数也永远和
  // 上面那排数字同源。
  const filtered = jobs.filter((j) => (
    (gradeFilter === '' || j.grade === gradeFilter)
    && (statusFilter === '' || j.status === statusFilter)
  ))
  const visible = filtered.slice(0, shown)

  /**
   * 标记状态。写回走的是 jobRadar Remote —— 和工作台之外的设置面板完全
   * 同一条路径，所以不存在两套写入语义打架的可能。
   */
  const mark = (id: string | number, next: string): void => {
    const face: JobRadarFace | undefined = ctx.jobRadar()
    if (face === undefined) return
    const key = String(id)
    setPending(key)
    face.setStatus(key, next)
      .then((res) => {
        if (!res?.ok) {
          setLoad((prev) => ({ ...prev, error: `标记失败：${res?.error ?? '未知原因'}` }))
          return
        }
        // The remote wrote the file and said so; reflect it locally instead of
        // paying for a second round-trip.
        setLoad((prev) => ({
          ...prev,
          error: '',
          jobs: prev.jobs.map((j) => (String(j.id) === key ? { ...j, status: next } : j)),
        }))
      })
      .catch((err: unknown) => {
        setLoad((prev) => ({ ...prev, error: `标记失败：${message(err)}` }))
      })
      .finally(() => { setPending('') })
  }

  if (load.status === 'missing') return sourceMissing()
  if (load.status === 'error') return sourceError(load.error, () => { setNonce(nonce + 1) })

  return h(
    'div',
    { style: { display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 880 } },
    toolbar(load, jobRadarProject.title(), () => { setNonce(nonce + 1) }),
    // A refused write or a failed re-read leaves the list on screen untouched,
    // so the reason has to be shown next to it — not swallowed.
    load.error === ''
      ? null
      : h(
        'div',
        {
          'data-job-error': 'yes',
          style: {
            padding: '8px 10px',
            borderRadius: 8,
            border: `1px solid ${T.border2}`,
            borderLeft: `3px solid ${T.danger}`,
            background: T.bgLayer1,
            color: T.danger,
            fontSize: 12,
            wordBreak: 'break-word',
          },
        },
        load.error,
      ),
    filterRow(gradeFilter, setGradeFilter, statusFilter, setStatusFilter, gradeCount, statusCount, jobs.length),
    list(visible, filtered.length, shown, setShown, pending, mark),
  )
}

// ---- header ---------------------------------------------------------------

/** 顶部：总数/分档计数 + 读取时间 + 刷新。 */
function toolbar(
  load: LoadState,
  title: string,
  onRefresh: () => void,
): ReactElement {
  const jobs = load.jobs
  const cells: [string, number][] = [
    ['总数', jobs.length],
    ...GRADES.map((g): [string, number] => [`${g} 级`, jobs.filter((j) => j.grade === g).length]),
    ['已投递', jobs.filter((j) => j.status === 'applied').length],
  ]
  const newest = newestDate(jobs)

  return h(
    'section',
    null,
    h(
      'div',
      {
        style: {
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          paddingBottom: 6,
          borderBottom: `1px solid ${T.border1}`,
        },
      },
      h('span', { style: { ...SECTION_TITLE, flex: '1 1 auto' } }, title),
      h(
        'span',
        { style: { ...CODE, color: T.textDim } },
        'remote.jobRadar',
      ),
      h(
        'span',
        { style: HINT, 'data-read-at': String(load.readAt) },
        load.status === 'loading' && load.readAt === 0
          ? '正在读取…'
          : `读取于 ${new Date(load.readAt).toLocaleTimeString()}`,
      ),
      h('button', { type: 'button', onClick: onRefresh, style: OUTLINE_BUTTON }, '刷新'),
    ),
    h(
      'div',
      { style: { display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 8, marginTop: 12 } },
      ...cells.map(([label, value]) => h(
        'div',
        {
          key: label,
          style: { padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border1}`, background: T.bgLayer1 },
        },
        h('div', { style: { fontSize: 11, color: T.text3 } }, label),
        h('div', { style: { fontSize: 20, fontWeight: 500, lineHeight: 1.5, color: T.text1 } }, String(value)),
      )),
    ),
    h(
      'div',
      { style: { ...HINT, marginTop: 8 } },
      newest === ''
        ? '快照里没有任何带日期的岗位。'
        : `快照里最新的岗位是 ${newest}。这是 jobs.json 的导出时间，不是抓取时间 —— 数字停住不动说明该跑一次 job-radar 抓取了。`,
    ),
  )
}

// ---- filters -------------------------------------------------------------

/** 等级与状态各一排筛选，计数就写在标签上。 */
function filterRow(
  gradeFilter: string,
  setGrade: (value: string) => void,
  statusFilter: string,
  setStatus: (value: string) => void,
  gradeCount: Record<string, number>,
  statusCount: Record<string, number>,
  total: number,
): ReactElement {
  return h(
    'section',
    { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
    h(
      'div',
      { style: { display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' } },
      h('span', { style: { ...SECTION_TITLE, width: 34 } }, '等级'),
      chip('全部', total, gradeFilter === '', T.text1, () => setGrade('')),
      ...GRADES.map((g) => chip(g, gradeCount[g] ?? 0, gradeFilter === g, gradeColor(g), () => setGrade(g))),
    ),
    h(
      'div',
      { style: { display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' } },
      h('span', { style: { ...SECTION_TITLE, width: 34 } }, '状态'),
      chip('全部', total, statusFilter === '', T.text1, () => setStatus('')),
      ...STATUSES.map((s) => chip(
        STATUS_LABEL[s] ?? s,
        statusCount[s] ?? 0,
        statusFilter === s,
        statusColor(s),
        () => setStatus(s),
      )),
    ),
  )
}

/** One filter chip. The count rides along so you can see what you are hiding. */
function chip(
  label: string,
  count: number,
  active: boolean,
  color: string,
  onClick: () => void,
): ReactElement {
  return h(
    'button',
    {
      key: label,
      type: 'button',
      'data-chip': label,
      'data-active': active ? 'yes' : 'no',
      'data-count': String(count),
      onClick,
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '3px 9px',
        borderRadius: 999,
        border: `1px solid ${active ? color : T.border2}`,
        background: active ? T.bgHover : 'transparent',
        color: active ? color : T.text2,
        font: 'inherit',
        fontSize: 12,
        cursor: 'pointer',
      },
    },
    h('span', null, label),
    h('span', { style: { color: T.textDim, fontFamily: T.mono, fontSize: 11 } }, String(count)),
  )
}

// ---- list ----------------------------------------------------------------

/** 岗位列表 + 「显示更多」。 */
function list(
  visible: readonly JobRecord[],
  matched: number,
  shown: number,
  setShown: (value: number) => void,
  pending: string,
  mark: (id: string | number, next: string) => void,
): ReactElement {
  if (visible.length === 0) {
    return h(
      'div',
      { style: { padding: '24px 0', color: T.text3, fontSize: 12 } },
      matched === 0 ? '当前筛选下没有岗位。' : '没有可显示的岗位。',
    )
  }
  return h(
    'section',
    { style: { display: 'flex', flexDirection: 'column' } },
    ...visible.map((job) => row(job, pending, mark)),
    matched > visible.length
      ? h(
        'button',
        {
          type: 'button',
          onClick: () => setShown(Number.MAX_SAFE_INTEGER),
          style: { ...OUTLINE_BUTTON, alignSelf: 'flex-start', marginTop: 12 },
        },
        `还有 ${matched - visible.length} 条，全部展开`,
      )
      : null,
  )
}

/** One job row: 等级 · 标题 · 元信息 · 评分明细 · 状态标记。 */
function row(
  job: JobRecord,
  pending: string,
  mark: (id: string | number, next: string) => void,
): ReactElement {
  const key = String(job.id)
  const details = job.details
  const hits = details?.skill_hits ?? []
  const busy = pending === key

  return h(
    'div',
    {
      key,
      'data-job': key,
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        padding: '10px 0 12px',
        borderBottom: `1px solid ${T.border1}`,
      },
    },
    // 标题行
    h(
      'div',
      { style: { display: 'flex', alignItems: 'baseline', gap: 8 } },
      h(
        'span',
        {
          style: {
            flex: '0 0 auto',
            minWidth: 20,
            textAlign: 'center',
            borderRadius: 5,
            padding: '0 5px',
            fontFamily: T.mono,
            fontSize: 11,
            fontWeight: 700,
            lineHeight: '17px',
            color: T.bgBase,
            background: gradeColor(job.grade),
          },
        },
        job.grade ?? '?',
      ),
      h(
        'span',
        { style: { flex: '1 1 auto', fontSize: 13.5, fontWeight: 500, color: T.text1, minWidth: 0 } },
        job.title || '(无标题)',
        job.url
          ? h(
            'a',
            {
              href: job.url,
              target: '_blank',
              rel: 'noreferrer',
              style: { marginLeft: 8, fontSize: 12, color: T.brand, textDecoration: 'none' },
            },
            '打开 ↗',
          )
          : null,
      ),
      h(
        'span',
        { style: { flex: '0 0 auto', fontFamily: T.mono, fontSize: 12, color: T.text2 } },
        String(job.score ?? 0),
      ),
      h(
        'span',
        { style: { flex: '0 0 auto', fontSize: 11, color: statusColor(job.status) } },
        STATUS_LABEL[job.status ?? ''] ?? job.status ?? '',
      ),
    ),
    // 元信息行
    h(
      'div',
      { style: { ...HINT, paddingLeft: 28 } },
      [job.company || '-', job.city || '-', salaryText(job), experienceText(job), job.education || '']
        .filter((part) => part !== '')
        .join(' · '),
    ),
    // 评分明细：回答"这条为什么是 A 级"
    details
      ? h(
        'div',
        { style: { ...CODE, paddingLeft: 28, color: T.text3 } },
        `技能 ${details.skill ?? 0} · 经验 ${details.experience ?? 0} · 公司 ${details.company ?? 0} · 新鲜 ${details.freshness ?? 0} · 通勤 ${details.commute ?? 0}`,
      )
      : null,
    hits.length > 0
      ? h(
        'div',
        { style: { display: 'flex', flexWrap: 'wrap', gap: 4, paddingLeft: 28 } },
        ...hits.slice(0, 6).map((hit) => h(
          'span',
          {
            key: hit,
            style: {
              fontSize: 11,
              color: T.text2,
              background: T.bgLayer2,
              borderRadius: 4,
              padding: '1px 5px',
            },
          },
          hit,
        )),
        hits.length > 6
          ? h('span', { style: { fontSize: 11, color: T.textDim } }, `+${hits.length - 6}`)
          : null,
      )
      : null,
    // 状态标记
    h(
      'div',
      { style: { display: 'flex', gap: 6, paddingLeft: 28, marginTop: 2 } },
      ...STATUSES.map((s) => h(
        'button',
        {
          key: s,
          type: 'button',
          'data-mark': `${key}:${s}`,
          disabled: busy,
          onClick: () => mark(job.id, s),
          style: {
            ...OUTLINE_BUTTON,
            fontSize: 11,
            padding: '1px 7px',
            borderColor: job.status === s ? statusColor(s) : T.border1,
            color: job.status === s ? statusColor(s) : T.text3,
            opacity: busy ? 0.5 : 1,
            cursor: busy ? 'default' : 'pointer',
          },
        },
        STATUS_LABEL[s],
      )),
    ),
  )
}

// ---- the two states that replace the whole body ---------------------------

/** 数据源没装载：说清楚是什么、为什么、怎么办。 */
function sourceMissing(): ReactElement {
  return h(
    'div',
    {
      'data-job-source': 'missing',
      style: {
        maxWidth: 620,
        margin: '16px auto 0',
        padding: '18px 20px',
        border: `1px dashed ${T.border2}`,
        borderRadius: 12,
        background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.text1 } }, 'Job Radar 数据源未装载'),
    h(
      'div',
      { style: { ...HINT, marginTop: 8 } },
      '这个项目自己不读文件 —— 岗位数据由 dsh-job-radar 插件通过 remote.jobRadar 提供。当前 profile 里没有解析到这个数据面，所以这里先空着。',
    ),
    h(
      'div',
      { style: { ...HINT, marginTop: 8 } },
      '要在工作台里看到岗位，把 dsh-job-radar 装进同一个 profile 并给它配好 dataDir（指向 job-radar 的 data 目录），然后重启宿主：',
    ),
    h(
      'div',
      {
        style: {
          ...CODE,
          marginTop: 8,
          padding: '8px 10px',
          borderRadius: 8,
          background: T.bgLayer2,
          border: `1px solid ${T.border1}`,
          wordBreak: 'break-all',
        },
      },
      'dsh plugin --profile <profile> add "file:<job-radar>/plugin/dsh-job-radar"',
    ),
    h(
      'div',
      { style: { ...HINT, marginTop: 8, color: T.textDim } },
      '注意：这个依赖是刻意做成可选的 —— 工作台的其余部分在它缺席时照常工作。',
    ),
  )
}

/** 读取失败（数据面在、但调用出错）。 */
function sourceError(error: string, onRetry: () => void): ReactElement {
  return h(
    'div',
    {
      'data-job-source': 'error',
      style: {
        maxWidth: 620,
        margin: '16px auto 0',
        padding: '14px 16px',
        border: `1px solid ${T.border2}`,
        borderLeft: `3px solid ${T.danger}`,
        borderRadius: 10,
        background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.danger } }, '读取岗位数据失败'),
    h('div', { style: { ...CODE, marginTop: 6, color: T.text2, wordBreak: 'break-word' } }, error),
    h(
      'button',
      { type: 'button', onClick: onRetry, style: { ...OUTLINE_BUTTON, marginTop: 10 } },
      '重试',
    ),
  )
}

// ---- helpers -------------------------------------------------------------

/** Glyph for the project: a radar sweep. */
function radarGlyph(): ReactElement {
  return h(
    'svg',
    {
      width: 14,
      height: 14,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 1.3,
      strokeLinecap: 'round',
      'aria-hidden': true,
      style: { flex: '0 0 auto' },
    },
    h('circle', { cx: 8, cy: 8, r: 5.6 }),
    h('circle', { cx: 8, cy: 8, r: 1.1, fill: 'currentColor', stroke: 'none' }),
    h('path', { d: 'M8 8l4.2-5.4' }),
  )
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Count jobs per distinct value of `pick`, skipping empty values. */
function tally(jobs: readonly JobRecord[], pick: (job: JobRecord) => string | undefined): Record<string, number> {
  const out: Record<string, number> = {}
  for (const job of jobs) {
    const key = pick(job)
    if (key === undefined || key === '') continue
    out[key] = (out[key] ?? 0) + 1
  }
  return out
}

function salaryText(job: JobRecord): string {
  const k = (value: number): string => `${Math.round(value / 1000)}K`
  if (job.salary_min && job.salary_max) return `${k(job.salary_min)}-${k(job.salary_max)}`
  if (job.salary_min) return `${k(job.salary_min)}+`
  if (job.salary_max) return `≤${k(job.salary_max)}`
  return '面议'
}

function experienceText(job: JobRecord): string {
  if (job.experience_min !== undefined && job.experience_max !== undefined) {
    return `${job.experience_min}-${job.experience_max} 年`
  }
  if (job.experience_min !== undefined) return `${job.experience_min} 年以上`
  return ''
}

/** The newest `created_at` in the snapshot, as a local date, or ''. */
function newestDate(jobs: readonly JobRecord[]): string {
  let newest = 0
  for (const job of jobs) {
    const at = job.created_at ? Date.parse(job.created_at) : NaN
    if (!Number.isNaN(at) && at > newest) newest = at
  }
  return newest === 0 ? '' : new Date(newest).toLocaleDateString()
}
