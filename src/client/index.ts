/**
 * dsh-plugin-workbench — client half.
 *
 * Contributes two slot occupants that together make one feature:
 *   - `sidebar.footer.action` — the entry at the sidebar foot that selects the
 *     workbench, badged when a plugin failed to start.
 *   - `main` (keyed `workbench`) — the panel itself, which takes over the centre
 *     column while it is selected.
 *
 * Those two ids are the same string (`PANEL_ID`, in `views.ts`) because that is
 * how the layout works: the centre renders the `main` entry whose key equals
 * `panelInfo.activePanelId`, and a sidebar entry selects one by calling
 * `ctx.layout.selectPanel(id)`. So this is not a floating window any more —
 * selecting the workbench *is* navigating the main view.
 *
 * The panel is a shell: a console of cards, a host page, and N project slots.
 * The slots live in `projects/slots.ts` and the contract they must satisfy is
 * in `projects/types.ts` — this file only builds the context they receive and
 * registers the two occupants.
 *
 * Data comes from the host's read-only inventory Remote
 * (`pluginInventory/list`), which every deployment mounting
 * `@deepseek-ai/dsh-host-plugin-inventory` provides. Nothing is fetched through
 * a private RPC, so this plugin adds no host-side API of its own.
 *
 * One project wants more than that: Job Radar reads a second Remote
 * (`remote.jobRadar`, mounted by the separate `dsh-job-radar` plugin). That one
 * is resolved **per call** through `ctx.reflect` and may legitimately be absent
 * — see `resolveOptionalRemote` below for why it is not an `inject`.
 *
 * Built by build.mjs into the module-loader factory bundle at
 * client/client.js; the only external is react.
 *
 * Requires dsh >= 0.1.5-rc.2: the `main` slot and `ctx.layout.selectPanel`
 * both arrive with the 0.1.5 layout. On an older host the sidebar entry mounts
 * but does nothing (see the defensive `main` registration at the end of `apply`).
 */
import { createControlRoom } from './ControlRoom.ts'
import { createHistoryStore } from './history.ts'
import { createHostView } from './HostView.ts'
import type { Translate } from './i18n.ts'
import { JOB_RADAR_ID, JobRadarView, jobRadarProject } from './projects/jobRadar.ts'
import { createProjectHost } from './projects/host.ts'
import { toJobRadarFace } from './projects/jobRadarRemote.ts'
import { PROJECT_SLOTS } from './projects/slots.ts'
import { TABLEWARE_RADAR_ID, TablewareRadarView, tablewareRadarProject } from './projects/tablewareRadar.ts'
import { toTablewareRadarFace } from './projects/tablewareRadarRemote.ts'
import type { ProjectContext } from './projects/types.ts'
import { createInventoryStore, createValueStore, type InventoryEntry } from './store.ts'
import { createTrigger } from './Trigger.ts'
import { CONTROL_ROOM_ID, HOST_ID, PANEL_ID, SYNC_ID, clampViewId, isKnownView, slotViewId } from './views.ts'
import { createWorkbench } from './Workbench.ts'
import { createSyncView } from './SyncView.ts'
import { unifiedRemoteContribution } from './unifiedRemotes.ts'
import { toWorkbenchSyncFace } from './workbenchSyncRemote.ts'

/** Dictionary namespace owned by this plugin. */
const NS = 'dsh-plugin-workbench'

/** The subset of the locale service this plugin touches (structural). */
interface LocaleService {
  register(namespace: string, dicts: { zh: Dict; en: Dict }): unknown
  bind(namespace: string): Translate
}

/** The subset of the slots service this plugin touches (structural). */
interface SlotsService {
  inject(slot: string, register: () => unknown): void
  register(meta: Record<string, unknown>, component: unknown): unknown
}

/**
 * The subset of `ctx.layout` this plugin uses — the cross-plugin panel
 * controller provided by `dsh-client-ui-layout`. Structural: the real class is
 * not importable from here.
 *
 * This service is why the plugin requires dsh >= 0.1.5-rc.2. The 0.1.1 layout
 * has a `LayoutController` with only `attachPanels`/`toggleSidebar`/
 * `openDetails`/`closeDetails`, and hard-wires the centre column to the
 * `conversation` slot — there is no panel mechanism to select into at all.
 */
interface LayoutService {
  /** Select a main panel by key, or `null` to return to the Conversation. */
  selectPanel(panelId: string | null): void
}

interface RemoteFailure {
  code: string
  message: string
}

interface RemoteResult<T> {
  ok: boolean
  value?: T
  error?: RemoteFailure
}

/** The generated client face of the host plugin-inventory Remote. */
interface PluginInventoryFace {
  list(): Promise<RemoteResult<{ entries: readonly InventoryEntry[] }>>
}

/** The client cordis context shape this plugin relies on (structural). */
interface WorkbenchClientContext {
  effect(callback: () => unknown, label?: string): void
  locale: LocaleService
  slots: SlotsService
  remote: {
    pluginInventory: PluginInventoryFace
    $mount(contribution: unknown): Promise<unknown>
  }
  /**
   * Cordis' reflection service, used for *optional* lookups. A real builtin,
   * not something to declare in `inject`.
   */
  reflect?: { get(name: string): unknown }
}

/**
 * Resolve a Remote that belongs to another, optional plugin.
 *
 * `remote.<namespace>` is a genuine service key (the api-gateway client mounts
 * each mounted namespace as one), but the namespace only exists once that
 * plugin's client half has mounted — which may be later than this one, or never.
 * So it is read through `reflect` on every call instead of being declared in
 * `inject`: declaring it would park the whole workbench, console and all,
 * waiting on a plugin that has nothing to do with it.
 *
 * Returns `undefined` when the plugin is absent, which projects are expected to
 * render as a state rather than an error.
 */
function resolveOptionalRemote(ctx: WorkbenchClientContext, name: string): unknown {
  return ctx.reflect?.get(name)
}

/**
 * Resolve the layout controller.
 *
 * `ctx.reflect.get` reads a service without the inject requirement, which is
 * what we want here: the layout belongs to the shipped frame, so it is always
 * there in practice, and a build without it should degrade to "the sidebar
 * button does nothing" rather than to a plugin that never starts.
 */
function resolveLayout(ctx: WorkbenchClientContext): LayoutService | undefined {
  return ctx.reflect?.get('layout') as LayoutService | undefined
}

export const name = 'dsh-plugin-workbench'

/**
 * `remote.pluginInventory` is a real service name: the api-remotes client
 * mounts each generated Remote under `remote.<namespace>`, so declaring it
 * makes this plugin wait until that inventory exists instead of racing it.
 */
export const inject = ['slots', 'locale', 'remote', 'remote.pluginInventory']

/**
 * Mount the client half.
 * @param ctx - client cordis context.
 */
export function apply(ctx: WorkbenchClientContext): void {
  void ctx.remote.$mount(unifiedRemoteContribution).then((dispose) => {
    ctx.effect(
      () => () => { if (typeof dispose === 'function') dispose() },
      'dsh-plugin-workbench: unified remote contribution',
    )
  })
  ctx.effect(
    () => ctx.locale.register(NS, { zh: DICT_ZH, en: DICT_EN }),
    'dsh-plugin-workbench: dictionaries',
  )
  const t = ctx.locale.bind(NS)

  /** Whether the workbench is the selected main panel. */
  const shown = createValueStore(false)
  /** Which view of the workbench is showing, and how we got there. */
  const history = createHistoryStore(CONTROL_ROOM_ID)

  const inventory = createInventoryStore(async () => {
    const result = await ctx.remote.pluginInventory.list()
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error?.code}: ${result.error?.message}`)
    }
    return result.value?.entries ?? []
  })

  /**
   * Select this plugin's main panel, or give the centre back.
   *
   * Robust to the panel not being registered yet — `ctx.layout.selectPanel`
   * throws for an unknown key — because the only thing that can happen is the
   * click being ignored, and a click that arrives before the slot is live is
   * not worth taking the plugin down for.
   */
  const select = (panelId: string | null): void => {
    const layout = resolveLayout(ctx)
    if (layout === undefined) return
    try {
      layout.selectPanel(panelId)
    } catch {
      // Either the `main` entry is not registered yet or this layout predates
      // `selectPanel`. Both mean "the click did nothing", which is not worth
      // taking the plugin down for.
    }
  }

  /**
   * The context every project receives. To hand projects more of the host
   * (another Remote, a service), add the field to `ProjectContext` in
   * `projects/types.ts` and supply it here — this is the only place that knows
   * what this plugin injects.
   */
  const projectCtx: ProjectContext = {
    t,
    inventory,
    // Adapter, not a cast: the mounted namespace speaks the gateway's envelope
    // and enforces parameter arity, while `JobRadarFace` promises neither.
    // See `projects/jobRadarRemote.ts`.
    jobRadar: () => toJobRadarFace(resolveOptionalRemote(ctx, 'remote.jobRadar')),
    // Same pattern for the tableware-radar data face: resolved per call through
    // `reflect`, never cached, never injected. See `projects/tablewareRadarRemote.ts`.
    tablewareRadar: () => toTablewareRadarFace(resolveOptionalRemote(ctx, 'remote.tablewareRadar')),
  }

  // One read at mount so the sidebar entry can badge a failed plugin before
  // the workbench has ever been selected. The Remote is injected, so it is
  // guaranteed present by the time `apply` runs.
  void inventory.refresh()

  // A fresh id sits beside the shipped entries in the sidebar slot; `order` only
  // decides where. The entry is additive and replaces nothing.
  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
    name: 'sidebar.footer.action',
    id: PANEL_ID,
    order: 60,
    label: () => t('action'),
  }, createTrigger({ shown, inventory, toggle: (show) => select(show ? PANEL_ID : null) }, t)))

  // The centre column. `key` is the id the layout dispatches on, so it has to
  // be the same string the sidebar entry selects.
  //
  // Registered defensively. `main` is a slot of the 0.1.5 layout; a host whose
  // layout predates it has no `main` at all, and an unknown slot must not take
  // the whole plugin — sidebar entry included — down with it. `select` is
  // already tolerant of a missing panel, so on such a host the failure mode is
  // simply that the entry is inert.
  try {
    ctx.slots.inject('main', () => ctx.slots.register({
      name: 'main',
      key: PANEL_ID,
    }, createWorkbench({
      shown,
      history,
      projects: PROJECT_SLOTS,
      projectCtx,
      workbenchSync: () => toWorkbenchSyncFace(resolveOptionalRemote(ctx, 'remote.workbenchSync')),
      close: () => select(null),
    }, t)))
  } catch {
    /* layout has no `main` slot — the sidebar entry stays inert. */
  }
}

type Dict = Record<string, string>

/**
 * Dictionaries are exported so the headless smoke test can assert against the
 * real copy instead of keeping a second hand-written copy that drifts.
 */
export const DICT_ZH: Dict = {
  action: '工作台',
  title: '可视化工作台',
  console: '控制台',
  host: '宿主插件',
  'host.subtitle': '本 profile 装载的插件与运行状态',
  back: '后退（Alt + ←）',
  forward: '前进（Alt + →）',
  exit: '返回会话',
  'section.projects': '项目',
  'section.host': '宿主',
  sync: '同步中心',
  'sync.subtitle': '只读检查本地与远端 main 的差异；本阶段不会提交、合并或推送。',
  'sync.cardSummary': '查看待上传、待下载和本地改动',
  'sync.readOnly': '只读预览',
  'sync.refresh': '获取远端并刷新',
  'sync.unavailable': '同步服务尚未装载，请确认统一工作台宿主插件正在运行。',
  'sync.branch': '当前分支',
  'sync.ahead': '待上传提交',
  'sync.behind': '待下载提交',
  'sync.changes': '本地改动',
  'sync.ready': '未发现会阻止同步预览的问题',
  'sync.fetchedAt': '检查时间',
  'sync.localChanges': '本地文件改动',
  'sync.localCommits': '待上传提交',
  'sync.remoteCommits': '待下载提交',
  'sync.clean': '工作区没有改动',
  'sync.none': '没有提交',
  slot: '项目',
  'slot.free': '预留',
  'slot.filled': '已接入',
  'slot.free.summary': '还没有接入项目',
  'slot.free.hint': '把下面这个对象填进 slots.ts 里对应的位置，它就会出现在这里。',
  'slot.free.file': '要改的文件',
  'slot.error': '渲染失败',
  'stat.total': '插件总数',
  'stat.active': '运行中',
  'stat.failed': '失败',
  'stat.disabled': '已禁用',
  refresh: '重新读取',
  readAt: '读取于',
  loading: '正在读取…',
  error: '读取失败',
  empty: '这个 profile 没有装载任何插件',
  'phase.pending': '待加载',
  'phase.loading': '加载中',
  'phase.active': '运行中',
  'phase.failed': '启动失败',
  'phase.unloading': '卸载中',
  'phase.none': '无实例',
}

export const DICT_EN: Dict = {
  action: 'Workbench',
  title: 'Workbench',
  console: 'Console',
  host: 'Host plugins',
  'host.subtitle': 'Plugins this profile composes, and how far each got',
  back: 'Back (Alt + ←)',
  forward: 'Forward (Alt + →)',
  exit: 'Back to chat',
  'section.projects': 'Projects',
  'section.host': 'Host',
  sync: 'Sync center',
  'sync.subtitle': 'Read-only comparison with origin/main. This phase never commits, rebases, or pushes.',
  'sync.cardSummary': 'Inspect uploads, downloads, and local changes',
  'sync.readOnly': 'read only',
  'sync.refresh': 'Fetch and refresh',
  'sync.unavailable': 'The sync service is not mounted.',
  'sync.branch': 'Branch',
  'sync.ahead': 'To upload',
  'sync.behind': 'To download',
  'sync.changes': 'Local changes',
  'sync.ready': 'No preview blockers found',
  'sync.fetchedAt': 'Checked',
  'sync.localChanges': 'Local file changes',
  'sync.localCommits': 'Commits to upload',
  'sync.remoteCommits': 'Commits to download',
  'sync.clean': 'Working tree is clean',
  'sync.none': 'No commits',
  slot: 'Project',
  'slot.free': 'reserved',
  'slot.filled': 'live',
  'slot.free.summary': 'No project wired up yet',
  'slot.free.hint': 'Drop the object below into the matching position in slots.ts and it shows up here.',
  'slot.free.file': 'File to edit',
  'slot.error': 'render failed',
  'stat.total': 'plugins',
  'stat.active': 'running',
  'stat.failed': 'failed',
  'stat.disabled': 'disabled',
  refresh: 'Refresh',
  readAt: 'read at',
  loading: 'Reading…',
  error: 'Read failed',
  empty: 'This profile composes no plugins',
  'phase.pending': 'pending',
  'phase.loading': 'loading',
  'phase.active': 'running',
  'phase.failed': 'failed',
  'phase.unloading': 'unloading',
  'phase.none': 'no fiber',
}

/**
 * Builders exposed for `scripts/smoke-client.mjs` only.
 *
 * The client bundle is not a public API, so nothing here is a compatibility
 * promise — it exists so the headless test can exercise the view components
 * and the project extension point without a browser.
 */
export const __testHooks = {
  CONTROL_ROOM_ID,
  HOST_ID,
  SYNC_ID,
  PANEL_ID,
  JOB_RADAR_ID,
  TABLEWARE_RADAR_ID,
  PROJECT_SLOTS,
  DICT_ZH,
  slotViewId,
  clampViewId,
  isKnownView,
  createValueStore,
  createInventoryStore,
  createHistoryStore,
  createControlRoom,
  createHostView,
  createProjectHost,
  createWorkbench,
  createSyncView,
  jobRadarProject,
  jobRadarView: JobRadarView,
  toJobRadarFace,
  tablewareRadarProject,
  tablewareRadarView: TablewareRadarView,
  toTablewareRadarFace,
  toWorkbenchSyncFace,
}
