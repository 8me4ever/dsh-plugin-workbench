/**
 * THESIS: “暮光任务舱”把首页变成结论优先的个人指挥台，拒绝等权入口卡片与装饰性欢迎区。
 * OWN-WORLD: 深石墨和冷蓝黑构成安静底面；钴蓝负责交互，青绿/琥珀/珊瑚红只表达状态。
 * STORY: 先确认全局是否正常，再看最匹配岗位与选品结论，最后按需进入详情或同步预览。
 * FIRST VIEWPORT: 紧凑标题和健康状态带在上，两块稳定的大型业务组件并列，同步状态横贯底部。
 * FORM: 固定、响应式的非对称 Bento 操作面；未来可扩展拖拽，但当前不牺牲位置记忆和扫描效率。
 * FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
 */
import { createElement as h, useEffect, useState, type ReactElement } from 'react'
import type { Translate } from './i18n.ts'
import type { JobRecord, ProjectContext, ProjectSlot, TablewareAnalysis } from './projects/types.ts'
import { useStoreValue, type InventoryStore } from './store.ts'
import { SYNC_ID, slotViewId } from './views.ts'
import type { SyncStatus, WorkbenchSyncFace } from './workbenchSyncRemote.ts'

interface Counts { total: number; active: number; failed: number; disabled: number }
interface DashboardData {
  jobs: readonly JobRecord[]
  analysis: TablewareAnalysis | null
  sync: SyncStatus | null
  jobError: string
  researchError: string
  syncError: string
}

export interface ControlRoomFace {
  inventory: InventoryStore
  projects: readonly ProjectSlot[]
  projectCtx?: ProjectContext
  workbenchSync?: () => WorkbenchSyncFace | undefined
  onOpen(id: string): void
}

const C = {
  bg: '#09111d', panel: '#0d1827', line: 'rgba(151, 177, 211, .14)',
  lineStrong: 'rgba(95, 150, 255, .28)', text: '#f2f6fb', text2: '#aebed1', text3: '#71849b',
  blue: '#66a3ff', cyan: '#46d9c2', amber: '#f4b86a', red: '#ff737c',
} as const

export function createControlRoom(face: ControlRoomFace, _t: Translate) {
  return function ControlRoom(): ReactElement {
    const inventory = useStoreValue(face.inventory)
    const [data, setData] = useState<DashboardData>({ jobs: [], analysis: null, sync: null, jobError: '', researchError: '', syncError: '' })
    const [refreshKey, setRefreshKey] = useState(0)

    useEffect(() => {
      let live = true
      const tasks: Promise<void>[] = []
      const jobFace = face.projectCtx?.jobRadar()
      if (jobFace !== undefined) tasks.push(jobFace.list().then((result) => {
        if (live) setData((old) => ({ ...old, jobs: result.jobs, jobError: '' }))
      }).catch((error: unknown) => { if (live) setData((old) => ({ ...old, jobError: message(error) })) }))
      const researchFace = face.projectCtx?.tablewareRadar()
      if (researchFace !== undefined) tasks.push(researchFace.getAnalysis().then((analysis) => {
        if (live) setData((old) => ({ ...old, analysis, researchError: '' }))
      }).catch((error: unknown) => { if (live) setData((old) => ({ ...old, researchError: message(error) })) }))
      const syncFace = face.workbenchSync?.()
      if (syncFace !== undefined) tasks.push(syncFace.preview().then((sync) => {
        if (live) setData((old) => ({ ...old, sync, syncError: '' }))
      }).catch((error: unknown) => { if (live) setData((old) => ({ ...old, syncError: message(error) })) }))
      void Promise.allSettled(tasks)
      return () => { live = false }
    }, [refreshKey])

    const counts: Counts = {
      total: inventory.entries.length,
      active: inventory.entries.filter((entry) => entry.fiberPhase === 'active').length,
      failed: inventory.entries.filter((entry) => entry.fiberPhase === 'failed').length,
      disabled: inventory.entries.filter((entry) => !entry.enabled).length,
    }
    const problems = counts.failed + Number(inventory.status === 'error') + Number(Boolean(data.syncError)) + Number(Boolean(data.jobError)) + Number(Boolean(data.researchError))
    return h('div', { 'data-dashboard': 'twilight', className: 'dsh-dash' },
      h('style', null, DASHBOARD_CSS),
      header(problems, data, () => { void face.inventory.refresh(); setRefreshKey((key) => key + 1) }),
      healthRail(problems, counts, data, inventory.error),
      h('main', { className: 'dsh-grid' },
        jobWidget(data, () => face.onOpen(slotViewId(0))),
        researchWidget(data, () => face.onOpen(slotViewId(1))),
        syncWidget(data.sync, data.syncError, () => face.onOpen(SYNC_ID)),
      ),
    )
  }
}

function header(problems: number, data: DashboardData, refresh: () => void): ReactElement {
  const ready = Number(data.jobs.length > 0) + Number(data.analysis !== null)
  return h('header', { className: 'dsh-head' }, h('div', null,
    h('h1', null, '个人工作台'),
    h('p', null, problems > 0 ? `${problems} 项状态需要关注` : `${ready} 个项目正常 · 关键数据已就绪`),
  ), h('button', { type: 'button', className: 'dsh-action', onClick: refresh }, refreshGlyph(), '刷新数据'))
}

function healthRail(problems: number, counts: Counts, data: DashboardData, inventoryError: string): ReactElement {
  const syncText = data.sync === null ? (data.syncError ? '同步状态读取失败' : '正在读取同步状态')
    : data.sync.blockers.length ? data.sync.blockers[0] : `${data.sync.branch} · ↑${data.sync.ahead} ↓${data.sync.behind}`
  return h('section', { className: 'dsh-health', 'aria-label': '系统状态' },
    statusCell(problems === 0 ? C.cyan : C.amber, problems === 0 ? '运行正常' : '需要关注', problems === 0 ? '所有核心服务可用' : `${problems} 项读取异常`),
    statusCell(C.blue, '业务项目', `${Number(data.jobs.length > 0) + Number(data.analysis !== null)} / 2 已就绪`),
    statusCell(data.sync?.blockers.length ? C.amber : C.cyan, '代码同步', syncText),
    inventoryError ? statusCell(C.red, '宿主状态读取失败', inventoryError)
      : counts.failed > 0 ? statusCell(C.red, '宿主异常', `${counts.failed} 个插件启动失败`) : h('div', { className: 'dsh-health-note' }, '只呈现需要行动的信息'),
  )
}

function statusCell(color: string, label: string, value: string): ReactElement {
  return h('div', { className: 'dsh-health-cell' }, h('span', { className: 'dsh-dot', style: { background: color } }),
    h('div', null, h('strong', null, label), h('span', null, value)))
}

function jobWidget(data: DashboardData, open: () => void): ReactElement {
  const jobs = [...data.jobs].filter((job) => job.status !== 'rejected').sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 5)
  const high = data.jobs.filter((job) => (job.grade === 'S' || job.grade === 'A') && job.status !== 'rejected').length
  return h('section', { className: 'dsh-widget dsh-widget-main' },
    widgetHead('slot:0', 'Job Radar', high > 0 ? `${high} 个高匹配岗位值得关注` : '查看当前最匹配的岗位', '查看全部', open, radarGlyph()),
    data.jobError ? errorLine(`岗位数据读取失败：${data.jobError}`) : jobs.length === 0 ? emptyLine('暂时没有可展示的岗位')
      : h('div', { className: 'dsh-job-list' }, ...jobs.map(jobRow)))
}

function jobRow(job: JobRecord): ReactElement {
  const hits = job.details?.skill_hits?.slice(0, 3) ?? []
  const place = [job.company, job.city].filter(Boolean).join(' · ') || '公司与地点待补充'
  return h('div', { key: String(job.id), className: 'dsh-job-row', 'data-dashboard-job': String(job.id) },
    h('span', { className: 'dsh-grade', 'data-grade': job.grade ?? '' }, job.grade ?? '—'),
    h('span', { className: 'dsh-job-copy' }, h('strong', null, job.title ?? '未命名岗位'), h('small', null, place),
      hits.length ? h('span', { className: 'dsh-reasons' }, hits.map((hit) => `# ${hit}`).join('   ')) : null),
    h('span', { className: 'dsh-score' }, h('strong', null, String(job.score ?? '—')), h('small', null, '匹配分')))
}

function researchWidget(data: DashboardData, open: () => void): ReactElement {
  const analysis = data.analysis
  const priorities = [...(analysis?.selection_priority ?? [])].sort((a, b) => (b.opportunity ?? 0) - (a.opportunity ?? 0))
  const opportunities = [...(analysis?.opportunities ?? [])].sort((a, b) => (b.opportunity ?? 0) - (a.opportunity ?? 0)).slice(0, 4)
  const lead = priorities[0]
  const conclusion = dimensionName(analysis, lead?.dimension)
  return h('section', { className: 'dsh-widget dsh-widget-main' },
    widgetHead('slot:1', '出海业务用户调研', conclusion ? `优先关注：${conclusion}` : '核心机会与关键因素', '查看详情', open, researchGlyph()),
    data.researchError ? errorLine(`调研数据读取失败：${data.researchError}`) : analysis === null ? emptyLine('分析结果尚未生成')
      : h('div', { className: 'dsh-research-body' }, lead?.reason ? h('p', { className: 'dsh-lead-reason' }, lead.reason) : null,
        h('div', { className: 'dsh-factor-list' }, ...opportunities.map((item, index) => h('div', { key: item.dimension ?? String(index), className: 'dsh-factor-row', 'data-dashboard-factor': item.dimension ?? String(index) },
          h('span', { className: 'dsh-factor-rank' }, String(index + 1).padStart(2, '0')),
          h('span', { className: 'dsh-factor-copy' }, h('strong', null, dimensionName(analysis, item.dimension) || item.dimension || '未命名维度'),
            h('small', null, item.supplier_action || '结合该维度继续验证产品方案')),
          h('span', { className: 'dsh-factor-value' }, formatScore(item.opportunity)),
        )))))
}

function syncWidget(status: SyncStatus | null, error: string, open: () => void): ReactElement {
  const clean = status !== null && status.files.length === 0 && status.ahead === 0 && status.behind === 0 && status.blockers.length === 0
  return h('section', { className: 'dsh-widget dsh-sync' },
    h('div', { className: 'dsh-sync-title' }, syncGlyph(), h('div', null, h('strong', null, '同步中心'), h('span', null, '代码、业务状态与精选结果'))),
    error ? h('span', { className: 'dsh-sync-error' }, error) : status === null ? h('span', { className: 'dsh-muted' }, '正在读取…')
      : h('div', { className: 'dsh-sync-stats' }, metric('分支', status.branch || '(detached)'), metric('待上传', String(status.ahead)), metric('待下载', String(status.behind)),
        h('span', { className: clean ? 'dsh-clean' : 'dsh-attention' }, clean ? '工作区干净' : `${status.files.length} 个本地改动`)),
    h('button', { type: 'button', className: 'dsh-link', 'data-card': SYNC_ID, 'data-claimed': 'yes', onClick: open }, '打开同步预览', chevron()))
}

function widgetHead(viewId: string, title: string, conclusion: string, action: string, open: () => void, iconNode: ReactElement): ReactElement {
  return h('div', { className: 'dsh-widget-head' }, iconNode,
    h('div', { className: 'dsh-widget-title' }, h('h2', null, title), h('p', null, conclusion)),
    h('button', { type: 'button', className: 'dsh-link', 'data-card': viewId, 'data-claimed': 'yes', onClick: open }, action, chevron()))
}

function dimensionName(analysis: TablewareAnalysis | null, id?: string): string {
  if (!id) return ''
  return analysis?.dimensions?.find((dimension) => dimension.id === id)?.name ?? id
}
function formatScore(value?: number): string { return typeof value !== 'number' ? '—' : value <= 1 ? `${Math.round(value * 100)}%` : value.toFixed(1) }
function metric(label: string, value: string): ReactElement { return h('span', { className: 'dsh-metric' }, h('small', null, label), h('strong', null, value)) }
function errorLine(text: string): ReactElement { return h('div', { className: 'dsh-error' }, text) }
function emptyLine(text: string): ReactElement { return h('div', { className: 'dsh-empty' }, text) }
function message(error: unknown): string { return error instanceof Error ? error.message : String(error) }

function icon(paths: string[]): ReactElement {
  return h('svg', { className: 'dsh-icon', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }, ...paths.map((d) => h('path', { key: d, d })))
}
function radarGlyph(): ReactElement { return icon(['M12 3a9 9 0 1 0 9 9', 'M12 7a5 5 0 1 0 5 5', 'M12 11a1 1 0 1 0 1 1', 'M12 12 19 5']) }
function researchGlyph(): ReactElement { return icon(['M4 19V9', 'M10 19V5', 'M16 19v-7', 'M22 19V3']) }
function syncGlyph(): ReactElement { return icon(['M20 7h-5V2', 'M4 17h5v5', 'M6.1 8A7 7 0 0 1 18 5l2 2', 'M17.9 16A7 7 0 0 1 6 19l-2-2']) }
function refreshGlyph(): ReactElement { return icon(['M20 11a8 8 0 1 0-2.3 5.7', 'M20 4v7h-7']) }
function chevron(): ReactElement { return icon(['m9 18 6-6-6-6']) }

const DASHBOARD_CSS = `
.dsh-dash{min-height:100%;margin:-20px -24px -28px;padding:26px 28px 34px;box-sizing:border-box;color:${C.text};background:radial-gradient(900px 260px at 55% -80px,rgba(53,112,225,.24),transparent 70%),linear-gradient(180deg,#0a1422 0%,${C.bg} 65%);font-family:var(--dsw-font-family,"PingFang SC","Microsoft YaHei",system-ui,sans-serif)}.dsh-dash *{box-sizing:border-box}.dsh-dash ::selection{background:rgba(102,163,255,.35);color:#fff}.dsh-dash button:focus-visible{outline:2px solid ${C.blue};outline-offset:3px}
.dsh-head{display:flex;align-items:center;gap:20px;margin-bottom:18px}.dsh-head>div{flex:1}.dsh-head h1{margin:0;font-size:25px;line-height:1.25;letter-spacing:-.025em}.dsh-head p{margin:5px 0 0;color:${C.text2};font-size:12px}.dsh-action,.dsh-link{display:inline-flex;align-items:center;gap:7px;border:1px solid ${C.lineStrong};background:rgba(15,31,50,.75);color:${C.text2};font:inherit;font-size:12px;border-radius:8px;padding:7px 10px;cursor:pointer}.dsh-action:hover,.dsh-link:hover{color:${C.text};border-color:rgba(102,163,255,.55);background:#142641}.dsh-action .dsh-icon,.dsh-link .dsh-icon{width:14px;height:14px}
.dsh-health{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid ${C.line};background:rgba(13,24,39,.82);border-radius:12px;margin-bottom:12px;overflow:hidden}.dsh-health-cell{display:flex;align-items:center;gap:10px;padding:13px 16px;border-right:1px solid ${C.line};min-width:0}.dsh-health-cell>div{display:flex;flex-direction:column;min-width:0}.dsh-health-cell strong{font-size:12px;font-weight:600}.dsh-health-cell span:not(.dsh-dot){font-size:10.5px;color:${C.text3};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dsh-dot{width:7px;height:7px;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,.35);flex:0 0 auto}.dsh-health-note{display:flex;align-items:center;justify-content:flex-end;padding:13px 16px;color:${C.text3};font-size:10.5px}
.dsh-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px}.dsh-widget{border:1px solid ${C.line};background:linear-gradient(145deg,rgba(16,30,48,.94),rgba(11,22,36,.96));border-radius:13px;box-shadow:0 12px 30px rgba(0,0,0,.18);overflow:hidden}.dsh-widget-main{grid-column:span 6;min-height:430px;padding:20px}.dsh-widget-head{display:flex;align-items:flex-start;gap:12px;padding-bottom:17px;border-bottom:1px solid ${C.line}}.dsh-icon{width:20px;height:20px;color:${C.blue};flex:0 0 auto}.dsh-widget-head>.dsh-icon{width:30px;height:30px;padding:6px;border:1px solid ${C.lineStrong};border-radius:9px;background:rgba(53,112,225,.1)}.dsh-widget-title{flex:1;min-width:0}.dsh-widget-title h2{margin:0;font-size:17px;line-height:1.25;letter-spacing:-.015em}.dsh-widget-title p{margin:6px 0 0;color:${C.text};font-size:18px;font-weight:650;line-height:1.35;letter-spacing:-.02em}
.dsh-job-list{display:flex;flex-direction:column;margin-top:5px}.dsh-job-row{display:flex;align-items:center;gap:12px;width:100%;min-height:67px;padding:10px 3px;border-bottom:1px solid ${C.line}}.dsh-job-row:last-child{border-bottom:0}.dsh-grade{display:grid;place-items:center;width:32px;height:32px;border:1px solid ${C.lineStrong};border-radius:8px;color:${C.blue};font-weight:700}.dsh-grade[data-grade="S"]{color:${C.cyan}}.dsh-job-copy{display:flex;flex-direction:column;gap:3px;flex:1;min-width:0}.dsh-job-copy strong{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dsh-job-copy small{color:${C.text3};font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dsh-reasons{color:${C.text2};font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dsh-score{display:flex;flex-direction:column;align-items:flex-end;min-width:42px}.dsh-score strong{font-size:18px;color:${C.blue};font-variant-numeric:tabular-nums}.dsh-score small{font-size:9px;color:${C.text3}}
.dsh-research-body{padding-top:16px}.dsh-lead-reason{margin:0 0 14px;padding:10px 12px;border:1px solid ${C.line};border-radius:9px;background:rgba(102,163,255,.055);color:${C.text2};font-size:11.5px;line-height:1.55}.dsh-factor-list{display:flex;flex-direction:column}.dsh-factor-row{display:flex;align-items:center;gap:12px;padding:13px 2px;border-bottom:1px solid ${C.line}}.dsh-factor-row:last-child{border-bottom:0}.dsh-factor-rank{font:600 10px/1 ui-monospace,monospace;color:${C.text3}}.dsh-factor-copy{display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}.dsh-factor-copy strong{font-size:13px}.dsh-factor-copy small{color:${C.text2};font-size:10.5px;line-height:1.45}.dsh-factor-value{color:${C.cyan};font-size:15px;font-weight:650;font-variant-numeric:tabular-nums}
.dsh-sync{grid-column:span 12;display:flex;align-items:center;gap:22px;padding:15px 18px}.dsh-sync-title{display:flex;align-items:center;gap:10px;min-width:190px}.dsh-sync-title>div{display:flex;flex-direction:column}.dsh-sync-title strong{font-size:13px}.dsh-sync-title span{font-size:10px;color:${C.text3};margin-top:3px}.dsh-sync-stats{display:flex;align-items:center;gap:22px;flex:1}.dsh-metric{display:flex;flex-direction:column;min-width:54px}.dsh-metric small{font-size:9.5px;color:${C.text3}}.dsh-metric strong{font-size:14px;margin-top:3px;font-variant-numeric:tabular-nums}.dsh-clean{color:${C.cyan};font-size:11px}.dsh-attention{color:${C.amber};font-size:11px}.dsh-sync-error,.dsh-error{color:${C.red};font-size:11px}.dsh-muted,.dsh-empty{color:${C.text3};font-size:11px}.dsh-empty,.dsh-error{padding:22px 2px}
@media(max-width:900px){.dsh-health{grid-template-columns:repeat(2,minmax(0,1fr))}.dsh-health-cell:nth-child(2){border-right:0}.dsh-widget-main{grid-column:span 12}.dsh-sync{align-items:flex-start;flex-wrap:wrap}.dsh-sync-stats{order:3;flex-basis:100%}}
@media(max-width:560px){.dsh-dash{padding:20px 16px 28px}.dsh-head{align-items:flex-start}.dsh-health{grid-template-columns:1fr}.dsh-health-cell{border-right:0;border-bottom:1px solid ${C.line}}.dsh-health-note{justify-content:flex-start}.dsh-widget-main{padding:16px;min-height:0}.dsh-widget-head{flex-wrap:wrap}.dsh-widget-head .dsh-link{margin-left:42px}.dsh-sync-stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.dsh-job-row{gap:8px}}
`
