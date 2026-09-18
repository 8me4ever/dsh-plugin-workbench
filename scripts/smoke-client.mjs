/**
 * Headless smoke test for the client half.
 *
 * The browser is the only real renderer for a DSH client bundle, but a broken
 * slot name, a bad view id or a project contract that does not actually work is
 * worth catching before anyone refreshes a page. This script therefore:
 *
 *   1. loads client/client.js through the same module-loader envelope the
 *      browser loader uses;
 *   2. applies the plugin against a stub cordis context that records every
 *      slot registration, every `ctx.layout.selectPanel` call and every Remote
 *      call;
 *   3. renders each view component with a minimal hook runtime and walks the
 *      returned element tree — including the extension point, by filling a
 *      slot with a fake project.
 *
 * It needs no browser, no DOM and no React — `react` is stubbed, so this is a
 * contract test (names, ids, wiring, view switching, history, render branches),
 * not a layout test. The things it structurally cannot see (a Remote that never
 * reaches the browser, the gateway envelope, parameter arity) are covered by
 * `scripts/browser-check.py`, which talks to the real host.
 *
 * Run: node scripts/smoke-client.mjs   (or: npm run smoke)
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const bundlePath = join(root, 'client', 'client.js')

let failures = 0
/** Assert one condition and report it. */
function check(label, ok, detail = '') {
  if (ok) {
    console.log(`  ok   ${label}`)
  } else {
    failures += 1
    console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`)
  }
}

// ---- 1. a minimal hook runtime -------------------------------------------
// Hook order is stable in each component, and none of them invokes another
// hook-owning component during their own render (children are returned as
// elements, never called), so one flat cursor per component stands in for
// React's dispatcher. Hook slots reset when the component identity changes,
// which is how "remount" is modelled here.
function createReactStub() {
  const state = { values: [], effects: [], cursor: 0, mounted: null }
  const react = {
    createElement(type, props, ...children) {
      return {
        type,
        props: props ?? {},
        children: children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false),
      }
    },
    useState(initial) {
      const slot = state.cursor++
      if (!(slot in state.values)) state.values[slot] = typeof initial === 'function' ? initial() : initial
      return [
        state.values[slot],
        (next) => { state.values[slot] = typeof next === 'function' ? next(state.values[slot]) : next },
      ]
    },
    useEffect(fn) { state.effects[state.cursor++] = fn },
  }
  return {
    react,
    /** Render a component and return its element tree. */
    render(Component, props) {
      if (Component !== state.mounted) {
        state.mounted = Component
        state.values = []
      }
      state.cursor = 0
      state.effects = []
      const tree = Component(props)
      return { tree, effects: state.effects }
    },
  }
}

// ---- 2. tree helpers ------------------------------------------------------
/** Concatenate every text node in a tree. */
function flat(node) {
  if (node === null || node === undefined || node === false) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(flat).join('')
  if (typeof node !== 'object') return ''
  return (node.children ?? []).map(flat).join('')
}

/** Find the first element matching a predicate. */
function find(node, pred) {
  if (node === null || node === undefined || typeof node !== 'object') return null
  if (Array.isArray(node)) {
    for (const child of node) {
      const hit = find(child, pred)
      if (hit) return hit
    }
    return null
  }
  if (pred(node)) return node
  for (const child of node.children ?? []) {
    const hit = find(child, pred)
    if (hit) return hit
  }
  return null
}

/** Every element matching a predicate. */
function findAll(node, pred, out = []) {
  if (node === null || node === undefined || typeof node !== 'object') return out
  if (Array.isArray(node)) {
    for (const child of node) findAll(child, pred, out)
    return out
  }
  if (pred(node)) out.push(node)
  for (const child of node.children ?? []) findAll(child, pred, out)
  return out
}

/** Run every recorded effect, ignoring the holes the cursor leaves behind. */
function runEffects(rendered) {
  for (const effect of rendered.effects) if (typeof effect === 'function') effect()
}

/** Collapse a tree to comparable text. */
const text = (node) => flat(node).replace(/\s+/g, ' ')

// ---- 3. load the bundle the way the browser loader does -------------------
const runtime = createReactStub()
const h = runtime.react.createElement
const bundle = readFileSync(bundlePath, 'utf8')
let envelope = null
/** Keydown listeners, so the Alt+arrow history shortcuts can be exercised. */
const keydownListeners = new Set()
globalThis.window = {
  __ModuleLoader__: { load: (e) => { envelope = e } },
  addEventListener: (type, fn) => { if (type === 'keydown') keydownListeners.add(fn) },
  removeEventListener: (type, fn) => { if (type === 'keydown') keydownListeners.delete(fn) },
}
/** Pretend the user pressed a key, optionally with modifiers held. */
function press(key, mods = {}) {
  for (const fn of [...keydownListeners]) fn({ key, altKey: false, ...mods })
}
new Function(bundle)()
check('bundle registers with __ModuleLoader__', envelope !== null)
check('bundle id is the plugin name', envelope?.id === 'dsh-plugin-workbench', String(envelope?.id))

const moduleExports = envelope.factory((name) => {
  if (name === 'react' || name === 'react/jsx-runtime') return runtime.react
  throw new Error(`unexpected external require: ${name}`)
})
check('exports name', moduleExports.name === 'dsh-plugin-workbench')
check('exports apply', typeof moduleExports.apply === 'function')
check(
  'injects the inventory Remote',
  Array.isArray(moduleExports.inject) && moduleExports.inject.includes('remote.pluginInventory'),
  JSON.stringify(moduleExports.inject),
)

const hooks = moduleExports.__testHooks
const ZH = moduleExports.DICT_ZH
const t = (key) => ZH[key] ?? key
check('exposes test hooks', hooks !== undefined && typeof hooks.createWorkbench === 'function')

// ---- 4. a stub cordis context --------------------------------------------
const ENTRIES = [
  { entryId: 'api-remotes', moduleName: '@deepseek-ai/dsh-api-remotes', enabled: true, fiberPhase: 'active' },
  { entryId: 'broken-one', moduleName: 'some-broken-plugin', enabled: true, fiberPhase: 'failed' },
  { entryId: 'off-one', moduleName: 'disabled-plugin', enabled: false, fiberPhase: null },
]

/** Two jobs, one per grade/status branch, shaped like a real jobs.json row. */
const JOB_RECORDS = [
  {
    id: 'job-1',
    title: '数据产品经理',
    company: '北京慧眼数据科技有限公司',
    city: '北京',
    salary_min: 22000,
    salary_max: 40000,
    experience_min: 1,
    experience_max: 5,
    education: '本科',
    url: 'https://example.com/job-1',
    score: 82,
    grade: 'A',
    status: 'new',
    created_at: '2026-08-27T08:05:30+00:00',
    details: { skill: 100, experience: 100, company: 0, freshness: 70, commute: 100, skill_hits: ['SQL', '数据分析'] },
  },
  { id: 'job-2', title: '数据分析师', company: '另一家', city: '上海', score: 51, grade: 'C', status: 'applied' },
]
const registrations = []
let readCount = 0
/** Every `ctx.layout.selectPanel` call apply() makes through the sidebar entry. */
const panelSelections = []

// The optional second Remote, provided by the separate dsh-job-radar plugin.
// `null` stands for "that plugin is not in this profile".
let jobFace = makeJobFace()
/**
 * Build a stub `remote.jobRadar` that records its calls.
 *
 * Deliberately shaped like the *raw* mounted namespace, not like the face the
 * project consumes: the gateway wraps every result in an `{ ok, value }`
 * envelope and rejects a call whose argument count differs from the descriptor
 * (`jobRadar/list` declares one parameter). Stubbing the friendly shape here
 * once hid a real bug — the adapter in `projects/jobRadarRemote.ts` is what
 * turns one into the other, so the stub has to keep the seam visible.
 */
function makeJobFace(records = JOB_RECORDS) {
  const calls = []
  return {
    calls,
    list: async (...args) => {
      calls.push(['list', ...args])
      return { ok: true, value: { jobs: records, total: records.length } }
    },
    stats: async (...args) => {
      calls.push(['stats', ...args])
      return { ok: true, value: { total: records.length } }
    },
    setStatus: async (...args) => {
      calls.push(['setStatus', ...args])
      return { ok: true, value: { ok: true } }
    },
  }
}

/**
 * What `ProjectContext.jobRadar()` returns once the real `apply()` has run:
 * the adapter, resolved lazily because `jobFace` is swapped between cases.
 */
const resolveJobRadar = () => hooks.toJobRadarFace(jobFace ?? undefined)

/** The cross-plugin panel controller, as `dsh-client-ui-layout` provides it. */
const layoutStub = { selectPanel: (id) => { panelSelections.push(id) } }

const ctx = {
  effect: (fn) => { fn() },
  locale: { register: () => ({}), bind: () => t },
  slots: {
    inject: (slot, register) => { register() },
    register: (meta, component) => { registrations.push({ meta, component }); return () => {} },
  },
  remote: {
    pluginInventory: {
      list: async () => { readCount += 1; return { ok: true, value: { entries: ENTRIES } } },
    },
  },
  // Optional lookups go through the reflection service; an unmounted namespace
  // is simply absent, which is the case this stub can toggle.
  reflect: {
    get: (name) => {
      if (name === 'remote.jobRadar') return jobFace ?? undefined
      if (name === 'layout') return layoutStub
      return undefined
    },
  },
}

let applyError = ''
try {
  moduleExports.apply(ctx)
} catch (err) {
  applyError = err.message
}
check('apply() runs without throwing', applyError === '', applyError)

// ---- 5. both slots registered with the right shape ------------------------
const trigger = registrations.find((r) => r.meta.name === 'sidebar.footer.action')
const panel = registrations.find((r) => r.meta.name === 'main')
check('registers sidebar.footer.action', trigger !== undefined)
check('registers the main panel', panel !== undefined)
check('sidebar entry uses the panel key as its id', trigger?.meta.id === hooks.PANEL_ID, String(trigger?.meta.id))
check('the main entry is keyed by that same id', panel?.meta.key === hooks.PANEL_ID, String(panel?.meta.key))
check('sidebar label is localized', typeof trigger?.meta.label === 'function' && trigger.meta.label() === ZH.action)
check('sidebar component is a function', typeof trigger?.component === 'function')
check('panel component is a function', typeof panel?.component === 'function')
// The whole point of this rework: the workbench is a main view, not an overlay.
check(
  'the workbench no longer occupies shell.overlay',
  registrations.every((r) => r.meta.name !== 'shell.overlay'),
  registrations.map((r) => r.meta.name).join(', '),
)
check(
  'the sidebar entry id and the main key are the same string',
  trigger?.meta.id === panel?.meta.key,
  `${trigger?.meta.id} vs ${panel?.meta.key}`,
)

await new Promise((r) => setTimeout(r, 0))
check('booting reads the host inventory once', readCount === 1, String(readCount))

// ---- 6. the sidebar entry selects the panel ------------------------------
const wide = runtime.render(trigger.component, { wide: true })
const wideText = text(wide.tree)
runEffects(wide)
check('trigger renders wide without throwing', wide.tree?.type === 'button')
check('trigger shows its label when wide', wideText.includes(ZH.action), wideText)
check('trigger badges the failed plugin', wideText.includes('1'), wideText)
check('a panel that is not showing is not current', wide.tree.props['aria-current'] === undefined)

wide.tree.props.onClick()
check('clicking the entry selects the main panel', panelSelections.at(-1) === hooks.PANEL_ID,
  JSON.stringify(panelSelections))

const rail = runtime.render(trigger.component, { wide: false })
check('trigger renders in the rail without throwing', rail.tree?.props?.style?.width === 32,
  String(rail.tree?.props?.style?.width))

// Selecting backwards is the same button: showing the panel flips it to unset.
const appliedPanel = runtime.render(panel.component, {})
runEffects(appliedPanel)
check('mounting the panel reports it as shown (shared store)', panelSelections.length > 0
  && runtime.render(trigger.component, { wide: true }).tree.props['aria-current'] === 'page')
runtime.render(trigger.component, { wide: true }).tree.props.onClick()
check('clicking again hands the centre back to the conversation', panelSelections.at(-1) === null,
  JSON.stringify(panelSelections))

// ---- 7. the workbench panel ----------------------------------------------
const now = Date.now()
/**
 * A fresh face plus its stores, for the panel under test.
 * @param projects - the slot list to render.
 * @param job - resolver for the optional jobRadar Remote.
 */
function makeFace(projects, job = resolveJobRadar) {
  const shown = hooks.createValueStore(false)
  const history = hooks.createHistoryStore(hooks.CONTROL_ROOM_ID)
  const inventory = hooks.createInventoryStore(async () => ENTRIES)
  inventory.set({ status: 'ready', entries: ENTRIES, readAt: now, error: '' })
  const closes = []
  return {
    shown,
    history,
    inventory,
    closes,
    face: {
      shown,
      history,
      projects,
      projectCtx: { t, inventory, jobRadar: job },
      close: () => { closes.push(true) },
    },
  }
}

/** All four slots unclaimed — what the console looks like before any project. */
const EMPTY_SLOTS = [null, null, null, null]

/** Render the panel and run its mount effects, the way the browser does. */
function mountPanel(Component) {
  const rendered = runtime.render(Component, {})
  runEffects(rendered)
  return rendered
}

/**
 * Which view the panel's content area is on.
 *
 * Read from the `data-view` attribute rather than by reaching into the child
 * element: the stub runtime renders one component per call, so the console and
 * the projects appear in the tree as *elements*, not as rendered output. Their
 * internals are covered by rendering them directly, further down.
 */
function bodyView(tree) {
  return find(tree, (n) => n.props?.['data-view'] !== undefined)?.props['data-view'] ?? null
}

const first = makeFace(hooks.PROJECT_SLOTS)
const Workbench = hooks.createWorkbench(first.face, t)
const opened = mountPanel(Workbench)
check('the panel renders without throwing', opened.tree !== null)
check('the panel identifies itself for the DOM', opened.tree?.props?.['data-workbench'] !== undefined)
check('the panel is labelled', opened.tree?.props?.['aria-label'] === ZH.title)
check('mounting the panel marks it shown', first.shown.get() === true)

const back = find(opened.tree, (n) => n.props?.['data-nav'] === 'back')
const forward = find(opened.tree, (n) => n.props?.['data-nav'] === 'forward')
check('the chrome has a back button', back !== null)
check('the chrome has a forward button', forward !== null)
check('the chrome is the first thing in the panel',
  opened.tree?.children?.[0]?.children?.some((n) => n?.type === 'button') === true)
check('back is disabled at the start of the history', back?.props.disabled === true)
check('forward is disabled at the start of the history', forward?.props.disabled === true)
check('the breadcrumb starts at the console',
  find(opened.tree, (n) => n.props?.['data-crumb'] === hooks.CONTROL_ROOM_ID) !== null)
check('the console is the view it opens on', bodyView(opened.tree) === hooks.CONTROL_ROOM_ID,
  String(bodyView(opened.tree)))

// Clicking a card is a navigation, so it must move the history, not just the
// view. The console is rendered directly here, the way the frame renders it.
const navConsole = hooks.createControlRoom(
  { inventory: first.inventory, projects: first.face.projects, onOpen: (id) => first.history.push(id) },
  t,
)
const navCards = findAll(runtime.render(navConsole, {}).tree, (n) => n.props?.['data-card'] !== undefined)
check('the panel opens on a console of cards', navCards.length === hooks.PROJECT_SLOTS.length + 1,
  String(navCards.length))
navCards.find((n) => n.props['data-card'] === 'slot:0')?.props.onClick()
check('clicking a card navigates into the project', first.history.current() === 'slot:0', first.history.current())
const afterCard = runtime.render(Workbench, {})
check('the panel switches its body to that project', bodyView(afterCard.tree) === 'slot:0', String(bodyView(afterCard.tree)))
check('the breadcrumb names the project', text(afterCard.tree).includes('Job Radar'), text(afterCard.tree).slice(0, 160))
check('back becomes available after navigating',
  find(afterCard.tree, (n) => n.props?.['data-nav'] === 'back')?.props.disabled === false)

find(afterCard.tree, (n) => n.props?.['data-nav'] === 'back')?.props.onClick()
check('back returns to the console', first.history.current() === hooks.CONTROL_ROOM_ID, first.history.current())
const afterBack = runtime.render(Workbench, {})
check('the console is drawn again', bodyView(afterBack.tree) === hooks.CONTROL_ROOM_ID)
check('the breadcrumb is a single segment again',
  findAll(afterBack.tree, (n) => n.props?.['data-crumb'] !== undefined).length === 1)
check('forward becomes available after going back',
  find(afterBack.tree, (n) => n.props?.['data-nav'] === 'forward')?.props.disabled === false)

find(afterBack.tree, (n) => n.props?.['data-nav'] === 'forward')?.props.onClick()
check('forward goes back into the project', first.history.current() === 'slot:0', first.history.current())

// Alt+arrows, the shortcut browsers use for the same two buttons.
press('ArrowLeft', { altKey: true })
check('Alt+ArrowLeft goes back', first.history.current() === hooks.CONTROL_ROOM_ID, first.history.current())
press('ArrowRight', { altKey: true })
check('Alt+ArrowRight goes forward', first.history.current() === 'slot:0', first.history.current())
press('ArrowLeft')
check('a bare ArrowLeft is left to the app', first.history.current() === 'slot:0', first.history.current())

// The breadcrumb's first segment is a link home.
const crumbHome = runtime.render(Workbench, {}).tree
find(crumbHome, (n) => n.props?.['data-crumb'] === hooks.CONTROL_ROOM_ID)?.props.onClick()
check('the breadcrumb links back to the console', first.history.current() === hooks.CONTROL_ROOM_ID,
  first.history.current())

// Leaving the panel is a layout concern, not a state we own.
find(runtime.render(Workbench, {}).tree, (n) => n.props?.title === ZH.exit)?.props.onClick()
check('the exit button hands the centre back', first.closes.length === 1, String(first.closes.length))

// The history survives leaving the panel and coming back — that is the point of
// keeping it in the plugin closure rather than in the component.
const resume = makeFace(hooks.PROJECT_SLOTS)
const WorkbenchResume = hooks.createWorkbench(resume.face, t)
mountPanel(WorkbenchResume)
resume.history.push(hooks.HOST_ID)
check('the panel opens on the view the history is on',
  bodyView(runtime.render(WorkbenchResume, {}).tree) === hooks.HOST_ID,
  String(bodyView(runtime.render(WorkbenchResume, {}).tree)))

// A history entry that no longer resolves must not draw a blank screen.
const SHORT_SLOTS = [null, null]
const stale = makeFace(SHORT_SLOTS)
const WorkbenchStale = hooks.createWorkbench(stale.face, t)
mountPanel(WorkbenchStale)
// 'slot:3' was recorded against a longer slot list than the one compiled in now.
stale.history.reset('slot:3')
check('a stale view id is repaired, not rendered blank',
  bodyView(runtime.render(WorkbenchStale, {}).tree) === hooks.CONTROL_ROOM_ID,
  String(bodyView(runtime.render(WorkbenchStale, {}).tree)))

// ---- 7b. the history store itself ----------------------------------------
const hist = hooks.createHistoryStore(hooks.CONTROL_ROOM_ID)
check('a fresh history has nothing to walk', !hist.canBack() && !hist.canForward())
hist.push('slot:0')
check('pushing an entry moves the cursor', hist.current() === 'slot:0' && hist.canBack())
hist.push('slot:0')
check('pushing the current view is a no-op', hist.get().stack.length === 2, String(hist.get().stack.length))
hist.push('host')
hist.back()
check('back moves the cursor without dropping entries',
  hist.current() === 'slot:0' && hist.canForward() && hist.get().stack.length === 3)
hist.push('slot:1')
check('a new navigation drops the forward entries',
  !hist.canForward() && hist.get().stack.length === 3, JSON.stringify(hist.get()))
hist.forward()
check('forward does nothing at the end', hist.current() === 'slot:1')
hist.reset('control-room')
check('reset collapses the stack', hist.get().stack.length === 1 && !hist.canBack())

check('an unknown view id falls back to the console', hooks.clampViewId('slot:9', 4) === hooks.CONTROL_ROOM_ID)
check('a slot inside the list stays valid', hooks.clampViewId('slot:3', 4) === 'slot:3')
check('the host page is always a valid view', hooks.clampViewId(hooks.HOST_ID, 0) === hooks.HOST_ID)
check('a truncated slot list invalidates the slot view', hooks.isKnownView('slot:2', 2) === false)

// ---- 8. the console -------------------------------------------------------
// Rendered against an all-empty slot list so the reserved-card branches below
// do not depend on what slots.ts currently ships.
const state = makeFace(EMPTY_SLOTS)
const openedViews = []
const ControlRoom = hooks.createControlRoom(
  { inventory: state.inventory, projects: state.face.projects, onOpen: (id) => openedViews.push(id) },
  t,
)
const room = runtime.render(ControlRoom, {})
const roomText = text(room.tree)
const roomCards = findAll(room.tree, (n) => n.props?.['data-card'] !== undefined)
check('the console renders without throwing', room.tree !== null)
check('the console is made of cards', roomCards.length === EMPTY_SLOTS.length + 1, String(roomCards.length))
check('every project slot has a card', roomCards.filter((n) => n.props['data-card'].startsWith('slot:')).length === 4)
check('the console names the project section', roomText.includes(ZH['section.projects']), roomText.slice(0, 120))
check('the console names the host section', roomText.includes(ZH['section.host']))
check('the console offers the host page as a card',
  roomCards.some((n) => n.props['data-card'] === hooks.HOST_ID))
check('an unclaimed slot is drawn as a placeholder',
  roomCards.filter((n) => n.props['data-claimed'] === 'no').length === 4)
check('the console counts the plugins', roomText.includes(ZH['stat.total']) && roomText.includes('3'),
  roomText.slice(0, 200))
check('the console reports the failure count', roomText.includes(ZH['stat.failed']))
roomCards.find((n) => n.props['data-card'] === 'slot:2')?.props.onClick()
check('a card opens its view', openedViews.at(-1) === 'slot:2', JSON.stringify(openedViews))
roomCards.find((n) => n.props['data-card'] === hooks.HOST_ID)?.props.onClick()
check('the host card opens the host page', openedViews.at(-1) === hooks.HOST_ID)

// The slot list actually shipped by slots.ts claims exactly one slot.
const shipped = makeFace(hooks.PROJECT_SLOTS)
const shippedRoom = runtime.render(
  hooks.createControlRoom({ inventory: shipped.inventory, projects: shipped.face.projects, onOpen: () => {} }, t),
  {},
)
check('slots.ts claims one of four slots', text(shippedRoom.tree).includes('1 / 4'), text(shippedRoom.tree).slice(-160))
check(
  'the claimed slot is marked as live',
  findAll(shippedRoom.tree, (n) => n.props?.['data-card']?.startsWith('slot:')
    && n.props['data-claimed'] === 'yes').length === 1,
)
check('the claimed card is named by its project', text(shippedRoom.tree).includes('Job Radar'))

// The read-failure branch, which the console shares with the host page.
const failing = hooks.createInventoryStore(async () => { throw new Error('boom') })
await failing.refresh()
const failingRoom = runtime.render(
  hooks.createControlRoom({ inventory: failing, projects: [], onOpen: () => {} }, t),
  {},
)
const failingText = text(failingRoom.tree)
check('the console renders a read error instead of throwing', failingText.includes('boom'), failingText.slice(0, 160))
check('the console handles an empty slot list', failingText.includes('0 / 0'))

// ---- 9. the host page -----------------------------------------------------
const hostPage = hooks.createHostView({ inventory: shipped.inventory }, t)
const hostText = text(runtime.render(hostPage, {}).tree)
const hostTree = runtime.render(hostPage, {}).tree
check('the host page lists every plugin',
  hostText.includes('@deepseek-ai/dsh-api-remotes') && hostText.includes('some-broken-plugin'), hostText.slice(0, 200))
check('the host page labels the failure', hostText.includes(ZH['phase.failed']))
check('the host page marks the disabled plugin', hostText.includes(ZH['stat.disabled']))
check('the host page puts breakage first',
  find(hostTree, (n) => n.props?.['data-plugin'] === 'broken-one') !== null)
check('the host page can reread the host', hostText.includes(ZH.refresh))
const failingHost = runtime.render(hooks.createHostView({ inventory: failing }, t), {}).tree
check('the host page reports a read error', text(failingHost).includes('boom'), text(failingHost).slice(0, 160))

// ---- 10. the project extension point --------------------------------------
const fake = {
  id: 'fake-project',
  title: () => '假项目',
  summary: () => '这是占位用的假项目',
  render: () => h('div', null, '来自假项目的内容'),
}
const ProjectHost = hooks.createProjectHost(
  { t, inventory: state.inventory, jobRadar: resolveJobRadar },
  t,
)

const emptySlot = runtime.render(ProjectHost, { slot: null, index: 0 })
const emptyText = text(emptySlot.tree)
check('an empty slot renders the reserved page', emptyText.includes(ZH['slot.free']))
check('the reserved page names its index', emptyText.includes('项目 01'), emptyText.slice(0, 80))
check('the reserved page names the file to edit', emptyText.includes('src/client/projects/slots.ts'))
check('the reserved page shows a project snippet', emptyText.includes('my-project'))

const filledSlot = runtime.render(ProjectHost, { slot: fake, index: 1 })
check('a filled slot renders the project', text(filledSlot.tree) === '来自假项目的内容', text(filledSlot.tree))

const broken = { id: 'broken', title: () => '坏项目', render: () => { throw new Error('kaboom') } }
const brokenSlot = runtime.render(ProjectHost, { slot: broken, index: 3 })
check('a throwing project is contained', text(brokenSlot.tree).includes('kaboom'), text(brokenSlot.tree).slice(0, 120))

const mixed = makeFace([fake, null, null, null])
const mixedTree = runtime.render(
  hooks.createControlRoom({ inventory: mixed.inventory, projects: mixed.face.projects, onOpen: () => {} }, t),
  {},
).tree
const mixedCards = findAll(mixedTree, (n) => n.props?.['data-card'] !== undefined)
check('a filled slot is named by the project', mixedCards.some((n) => text(n).includes('假项目')),
  mixedCards.map((n) => text(n)).join(' | '))
// Three slots are still empty, so they keep the generated 项目 NN name. The
// filled one is named by the project and must not be counted here.
check('filling one slot leaves the others reserved',
  mixedCards.filter((n) => n.props['data-claimed'] === 'no').length === 3,
  mixedCards.map((n) => text(n)).join(' | '))
check('the console counts claimed slots', text(mixedTree).includes('1 / 4'))
check('a reserved card is still clickable',
  mixedCards.find((n) => n.props['data-card'] === 'slot:1')?.props.onClick !== undefined)

// ---- 11. project 01: Job Radar -------------------------------------------
// Drives the real project view, not a fake one. `render(ctx)` only hands the
// context to a component; that component owns the state, so the test renders it
// directly — the same treatment the console gets.
const JobRadarView = hooks.jobRadarView

/**
 * Render a hook-owning view, run its effects, let the pending read settle, then
 * render again. Two renders with the same component identity keep the hook
 * slots, which is how the resolved state becomes visible here.
 */
async function settle(Component, props) {
  const firstRender = runtime.render(Component, props)
  runEffects(firstRender)
  await new Promise((resolve) => setTimeout(resolve, 0))
  return runtime.render(Component, props)
}

/** A context carrying whatever jobRadar handle the case under test wants. */
function jobCtx(jobRadar, t2 = t) {
  return { t: t2, inventory: state.inventory, jobRadar }
}

check('project 01 is the Job Radar project', hooks.PROJECT_SLOTS[0]?.id === hooks.JOB_RADAR_ID,
  String(hooks.PROJECT_SLOTS[0]?.id))
check('project 01 declares a title and a summary',
  hooks.PROJECT_SLOTS[0]?.title() === 'Job Radar'
  && typeof hooks.PROJECT_SLOTS[0]?.summary() === 'string'
  && hooks.PROJECT_SLOTS[0].summary() !== '')
check('project 01 draws its own icon', hooks.PROJECT_SLOTS[0]?.icon()?.type === 'svg')

jobFace = makeJobFace()
const ready = await settle(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
const readyText = text(ready.tree)
check('the project reads the jobRadar Remote on mount',
  jobFace.calls.some((c) => c[0] === 'list'), JSON.stringify(jobFace.calls))
// `jobRadar/list` declares exactly one parameter and the gateway checks arity,
// so `list()` must never leave the building without its filter argument.
check('every list call carries the one argument the descriptor declares',
  jobFace.calls.filter((c) => c[0] === 'list').every((c) => c.length === 2),
  JSON.stringify(jobFace.calls))
check('stats is called with no arguments, as declared',
  jobFace.calls.filter((c) => c[0] === 'stats').every((c) => c.length === 1),
  JSON.stringify(jobFace.calls))
// The adapter unwraps `{ ok, value }` — without that the list renders empty
// and every row below would be missing while `ok` looked healthy.
check('the adapter unwraps the gateway envelope',
  (await resolveJobRadar().list()).jobs.length === JOB_RECORDS.length)
check('the project lists the jobs it got back',
  readyText.includes('数据产品经理') && readyText.includes('数据分析师'), readyText.slice(0, 200))
check('a row carries grade, score and status',
  readyText.includes('82') && readyText.includes('新发现') && readyText.includes('已投递'))
check('a row carries the compact metadata line',
  readyText.includes('北京慧眼数据科技有限公司') && readyText.includes('22K-40K') && readyText.includes('1-5 年'),
  readyText.slice(0, 400))
check('a row explains its score', readyText.includes('技能 100') && readyText.includes('新鲜 70'))
check('a row shows the matched skills', readyText.includes('SQL'))
check('the snapshot date is surfaced', readyText.includes('快照里最新的岗位'), readyText.slice(0, 300))
check('the source is named on screen', readyText.includes('remote.jobRadar'))

// Filtering is local, so switching a chip must not re-read.
const listCalls = jobFace.calls.filter((c) => c[0] === 'list').length
const cChip = find(ready.tree, (n) => n.props?.['data-chip'] === 'C')
check('the grade chips carry their counts', cChip?.props['data-count'] === '1', String(cChip?.props['data-count']))
cChip?.props.onClick()
const filtered = runtime.render(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
check('filtering by grade hides the other grades',
  !text(filtered.tree).includes('数据产品经理') && text(filtered.tree).includes('数据分析师'),
  text(filtered.tree).slice(0, 160))
check('filtering does not re-read the snapshot',
  jobFace.calls.filter((c) => c[0] === 'list').length === listCalls)
find(filtered.tree, (n) => n.props?.['data-chip'] === '全部')?.props.onClick()

// Marking writes through the same Remote the standalone panel uses.
const backToAll = runtime.render(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
const appliedChip = find(backToAll.tree, (n) => n.props?.['data-chip'] === '已投递')
check('the applied count starts at 1', appliedChip?.props['data-count'] === '1', String(appliedChip?.props['data-count']))
find(backToAll.tree, (n) => n.props?.['data-mark'] === 'job-1:applied')?.props.onClick()
await new Promise((resolve) => setTimeout(resolve, 0))
const marked = runtime.render(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
check('marking calls setStatus on the Remote',
  jobFace.calls.some((c) => c[0] === 'setStatus' && c[1] === 'job-1' && c[2] === 'applied'),
  JSON.stringify(jobFace.calls))
check('marking updates the row without a re-read',
  find(marked.tree, (n) => n.props?.['data-chip'] === '已投递')?.props['data-count'] === '2',
  String(find(marked.tree, (n) => n.props?.['data-chip'] === '已投递')?.props['data-count']))

// A rejected write surfaces instead of being swallowed. The transport succeeds
// (`ok: true`) and the *host* refuses — the case the envelope makes easy to get
// wrong, since a naive reader would see `ok` and report success.
jobFace = makeJobFace()
jobFace.setStatus = async (...args) => {
  jobFace.calls.push(['setStatus', ...args])
  return { ok: true, value: { ok: false, error: '快照只读' } }
}
const denied = await settle(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
find(denied.tree, (n) => n.props?.['data-mark'] === 'job-1:applied')?.props.onClick()
await new Promise((resolve) => setTimeout(resolve, 0))
const denied2 = runtime.render(JobRadarView, { ctx: jobCtx(resolveJobRadar) })
check('a refused write is reported', text(denied2.tree).includes('快照只读'), text(denied2.tree).slice(0, 200))

// The optional dependency is absent: a state, not a crash.
const missing = await settle(JobRadarView, { ctx: jobCtx(() => undefined) })
const missingText = text(missing.tree)
check('a missing data source renders an explanation, not a throw',
  find(missing.tree, (n) => n.props?.['data-job-source'] === 'missing') !== null)
check('the explanation names the plugin to install',
  missingText.includes('dsh-job-radar') && missingText.includes('dataDir'), missingText.slice(0, 240))

// A failing read is reported next to a retry, and the project stays mounted.
const brokenFace = {
  list: async () => { throw new Error('boom-remote') },
  stats: async () => ({ ok: true, value: {} }),
  setStatus: async () => ({ ok: true, value: { ok: true } }),
}
const brokenRead = await settle(JobRadarView, { ctx: jobCtx(() => hooks.toJobRadarFace(brokenFace)) })
check('a failing read is reported', text(brokenRead.tree).includes('boom-remote'), text(brokenRead.tree).slice(0, 200))

// A namespace that mounted only halfway must read as "absent", not crash the
// adapter or render a half-drawn screen.
const halfFace = { list: async () => ({ ok: true, value: { jobs: [], total: 0 } }) }
check('a half-mounted namespace resolves to undefined',
  hooks.toJobRadarFace(halfFace) === undefined)
check('a non-object namespace resolves to undefined',
  hooks.toJobRadarFace(undefined) === undefined && hooks.toJobRadarFace('nope') === undefined)

// And the whole thing still survives the panel that hosts it.
const withProject = makeFace(hooks.PROJECT_SLOTS)
const WorkbenchProject = hooks.createWorkbench(withProject.face, t)
const projectPanelTree = mountPanel(WorkbenchProject).tree
check('the panel opens on the console', bodyView(projectPanelTree) === hooks.CONTROL_ROOM_ID)
withProject.history.push('slot:0')
const projectView = runtime.render(WorkbenchProject, {})
check('the panel routes to the job radar project', bodyView(projectView.tree) === 'slot:0',
  String(bodyView(projectView.tree)))
check('the project page is not the reserved placeholder',
  !text(projectView.tree).includes('my-project'), text(projectView.tree).slice(0, 120))

// Finally, the component `apply()` actually registered — the real stores end to
// end, rather than a face built by this test.
const registeredPanel = mountPanel(panel.component)
check('the panel registered by apply() opens on the console',
  bodyView(registeredPanel.tree) === hooks.CONTROL_ROOM_ID,
  String(bodyView(registeredPanel.tree)))

console.log(failures === 0 ? '\nall checks passed' : `\n${failures} check(s) failed`)
process.exit(failures === 0 ? 0 : 1)
