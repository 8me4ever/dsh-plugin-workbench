window.__ModuleLoader__.load({ id: "dsh-plugin-workbench", factory: (require) => {
var module = { exports: {} };
var exports = module.exports;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name2 in all)
    __defProp(target, name2, { get: all[name2], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/client/index.ts
var index_exports = {};
__export(index_exports, {
  DICT_EN: () => DICT_EN,
  DICT_ZH: () => DICT_ZH,
  __testHooks: () => __testHooks,
  apply: () => apply,
  inject: () => inject,
  name: () => name
});
module.exports = __toCommonJS(index_exports);

// src/client/ControlRoom.ts
var import_react3 = require("react");

// src/client/parts.ts
var import_react = require("react");

// src/client/tokens.ts
var T = {
  font: 'var(--dsw-font-family, system-ui, -apple-system, "Segoe UI", sans-serif)',
  mono: "var(--ds-font-family-code, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)",
  /** Surfaces, from the page itself outwards to raised cards. */
  bgBase: "var(--dsw-alias-bg-base, #FFFFFF)",
  bgLayer1: "var(--dsw-alias-bg-layer-1, #FFFFFF)",
  bgLayer2: "var(--dsw-alias-bg-layer-2, #F4F5F6)",
  bgHover: "var(--dsw-alias-interactive-bg-hover, rgba(15, 17, 21, 0.06))",
  /** Hairlines. l1 is the faintest, l3 the most assertive. */
  border1: "var(--dsw-alias-border-l1, rgba(15, 17, 21, 0.08))",
  border2: "var(--dsw-alias-border-l2, rgba(15, 17, 21, 0.14))",
  border3: "var(--dsw-alias-border-l3, rgba(15, 17, 21, 0.22))",
  /** Text ramp: primary → secondary → tertiary → dimmed. */
  text1: "var(--dsw-alias-label-primary, #0F1115)",
  text2: "var(--dsw-alias-label-secondary, #61666B)",
  text3: "var(--dsw-alias-label-tertiary, #81858C)",
  textDim: "var(--dsw-alias-label-dimmed, #ADB2B8)",
  /** Semantic accents. */
  brand: "var(--dsw-alias-brand-primary, #4D6BFE)",
  info: "var(--dsw-alias-state-business-primary, #185FA5)",
  ok: "var(--dsw-alias-state-success-primary, #0F6E56)",
  warn: "var(--dsw-alias-state-warn-label, #854F0B)",
  danger: "var(--dsw-alias-state-error-primary, #E24B4A)",
  elevation: "var(--dsw-elevation-prominent, 0 12px 32px rgba(15, 17, 21, 0.16))"
};
var SCROLL = {
  overflowY: "auto",
  overflowX: "hidden",
  scrollbarWidth: "thin"
};
var OUTLINE_BUTTON = {
  border: `1px solid ${T.border2}`,
  borderRadius: 6,
  background: "transparent",
  color: "inherit",
  font: "inherit",
  fontSize: 12,
  padding: "2px 8px",
  cursor: "pointer"
};
var HINT = {
  color: T.text3,
  fontSize: 12,
  lineHeight: 1.6
};
var CODE = {
  fontFamily: T.mono,
  fontSize: 11.5,
  lineHeight: 1.6,
  color: T.text2
};
var SECTION_TITLE = {
  fontSize: 11,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: T.text3,
  fontWeight: 500
};
function phaseColor(phase) {
  switch (phase) {
    case "active":
      return T.ok;
    case "loading":
      return T.info;
    case "pending":
      return T.warn;
    case "failed":
      return T.danger;
    case "unloading":
      return T.text3;
    default:
      return T.textDim;
  }
}

// src/client/parts.ts
function sectionHeader(title, right = []) {
  return (0, import_react.createElement)(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 10,
        paddingBottom: 6,
        borderBottom: `1px solid ${T.border1}`
      }
    },
    (0, import_react.createElement)("span", { style: { ...SECTION_TITLE, flex: "1 1 auto" } }, title),
    ...right.filter((node) => node !== null)
  );
}
function notice(text, color) {
  return (0, import_react.createElement)(
    "div",
    { style: { padding: "12px 0", color, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word" } },
    text
  );
}
function statusStrip(t, state, counts, onRefresh) {
  const cells = [
    [t("stat.total"), counts.total, T.text1],
    [t("stat.active"), counts.active, T.ok],
    [t("stat.failed"), counts.failed, counts.failed > 0 ? T.danger : T.textDim],
    [t("stat.disabled"), counts.disabled, counts.disabled > 0 ? T.text3 : T.textDim]
  ];
  return (0, import_react.createElement)(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 16,
        padding: "9px 12px",
        borderRadius: 10,
        border: `1px solid ${T.border1}`,
        background: T.bgLayer2
      }
    },
    ...cells.map(([label, value, color]) => (0, import_react.createElement)(
      "div",
      { key: label, style: { display: "flex", alignItems: "baseline", gap: 6 } },
      (0, import_react.createElement)("span", { style: { fontSize: 11, color: T.text3 } }, label),
      (0, import_react.createElement)("span", { style: { fontSize: 16, fontWeight: 500, lineHeight: 1.2, color } }, String(value))
    )),
    (0, import_react.createElement)("span", { style: { flex: "1 1 auto" } }),
    state.readAt > 0 ? (0, import_react.createElement)("span", { key: "at", style: HINT }, `${t("readAt")} ${new Date(state.readAt).toLocaleTimeString()}`) : null,
    (0, import_react.createElement)("button", { key: "refresh", type: "button", onClick: onRefresh, style: OUTLINE_BUTTON }, t("refresh"))
  );
}

// src/client/store.ts
var import_react2 = require("react");
function createValueStore(initial) {
  let value = initial;
  const listeners = /* @__PURE__ */ new Set();
  return {
    get: () => value,
    set(next) {
      if (next === value) return;
      value = next;
      for (const listener of listeners) listener();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    }
  };
}
function createInventoryStore(read) {
  const store = createValueStore({ status: "idle", entries: [], readAt: 0, error: "" });
  let inFlight = null;
  const refresh = () => {
    if (inFlight !== null) return inFlight;
    store.set({ ...store.get(), status: "loading" });
    inFlight = read().then((entries) => {
      store.set({ status: "ready", entries, readAt: Date.now(), error: "" });
    }).catch((err) => {
      const message2 = err instanceof Error ? err.message : String(err);
      const previous = store.get();
      store.set({ status: "error", entries: previous.entries, readAt: previous.readAt, error: message2 });
    }).finally(() => {
      inFlight = null;
    });
    return inFlight;
  };
  return {
    get: store.get,
    set: store.set,
    subscribe: store.subscribe,
    refresh
  };
}
function useStoreValue(store) {
  const [value, setValue] = (0, import_react2.useState)(store.get());
  (0, import_react2.useEffect)(() => store.subscribe(() => setValue(store.get())), [store]);
  return value;
}

// src/client/views.ts
var CONTROL_ROOM_ID = "control-room";
var HOST_ID = "host";
var PANEL_ID = "workbench";
function slotViewId(index) {
  return `slot:${index}`;
}
function slotIndexOf(viewId) {
  if (!viewId.startsWith("slot:")) return null;
  const index = Number.parseInt(viewId.slice(5), 10);
  return Number.isInteger(index) && index >= 0 ? index : null;
}
function pad2(n) {
  return n < 10 ? `0${n}` : String(n);
}
function slotLabel(index, t) {
  return `${t("slot")} ${pad2(index + 1)}`;
}
function isKnownView(viewId, slotCount) {
  if (viewId === CONTROL_ROOM_ID || viewId === HOST_ID) return true;
  const index = slotIndexOf(viewId);
  return index !== null && index < slotCount;
}
function clampViewId(viewId, slotCount) {
  return isKnownView(viewId, slotCount) ? viewId : CONTROL_ROOM_ID;
}

// src/client/ControlRoom.ts
function createControlRoom(face, t) {
  return function ControlRoom() {
    const state = useStoreValue(face.inventory);
    const entries = state.entries;
    const counts = {
      total: entries.length,
      active: entries.filter((e) => e.fiberPhase === "active").length,
      failed: entries.filter((e) => e.fiberPhase === "failed").length,
      disabled: entries.filter((e) => !e.enabled).length
    };
    const claimed = face.projects.filter((p) => p !== null && p !== void 0).length;
    return (0, import_react3.createElement)(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: 22, maxWidth: 880 } },
      statusStrip(t, state, counts, () => {
        void face.inventory.refresh();
      }),
      // A failed read is worth saying out loud on the console: the counters above
      // would otherwise read as "this profile really has zero plugins", and the
      // host card would send you to a page that says nothing either. The cards
      // below stay usable — they do not depend on the read.
      state.status === "error" ? notice(state.error || t("error"), T.danger) : entries.length === 0 && state.status === "loading" ? notice(t("loading"), T.text3) : null,
      section(
        t("section.projects"),
        [`${claimed} / ${face.projects.length}`],
        cardGrid(face.projects.map((slot, index) => projectCard(t, slot, index, face.onOpen)))
      ),
      section(
        t("section.host"),
        [],
        cardGrid([hostCard(t, counts, face.onOpen)])
      )
    );
  };
}
function section(title, meta, children) {
  return (0, import_react3.createElement)(
    "section",
    { style: { display: "flex", flexDirection: "column" } },
    sectionHeader(
      title,
      meta.map((value) => (0, import_react3.createElement)("span", { key: value, style: HINT }, value))
    ),
    children
  );
}
function cardGrid(cards) {
  return (0, import_react3.createElement)(
    "div",
    {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(216px, 1fr))",
        gap: 10,
        marginTop: 12
      }
    },
    ...cards
  );
}
function projectCard(t, slot, index, onOpen) {
  const claimed = slot !== null && slot !== void 0;
  const title = claimed ? slot.title() : slotLabel(index, t);
  const summary = claimed && typeof slot.summary === "function" ? slot.summary() : t("slot.free.summary");
  return card({
    viewId: slotViewId(index),
    claimed,
    eyebrow: String(index + 1).padStart(2, "0"),
    title,
    summary,
    tag: claimed ? t("slot.filled") : t("slot.free"),
    tagColor: claimed ? T.ok : T.text3,
    icon: claimed && typeof slot.icon === "function" ? slot.icon() : null,
    onOpen
  });
}
function hostCard(t, counts, onOpen) {
  const summary = counts.failed > 0 ? `${counts.active} / ${counts.total} ${t("stat.active")} \xB7 ${counts.failed} ${t("stat.failed")}` : `${counts.active} / ${counts.total} ${t("stat.active")}`;
  return card({
    viewId: HOST_ID,
    claimed: true,
    eyebrow: "\u2014",
    title: t("host"),
    summary,
    tag: counts.failed > 0 ? t("stat.failed") : t("slot.filled"),
    tagColor: counts.failed > 0 ? T.danger : T.text3,
    icon: hostGlyph(),
    onOpen
  });
}
function card(props) {
  return (0, import_react3.createElement)(
    "button",
    {
      key: props.viewId,
      type: "button",
      // Stable hook for the headless smoke test and the browser check.
      "data-card": props.viewId,
      "data-claimed": props.claimed ? "yes" : "no",
      onClick: () => props.onOpen(props.viewId),
      style: {
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        gap: 6,
        width: "100%",
        boxSizing: "border-box",
        textAlign: "left",
        padding: "11px 13px 12px",
        borderRadius: 10,
        // Dashed while free: the outline is the only thing telling you this
        // card is a placeholder rather than a project.
        border: `1px ${props.claimed ? "solid" : "dashed"} ${props.claimed ? T.border1 : T.border2}`,
        background: T.bgLayer1,
        color: "inherit",
        font: "inherit",
        cursor: "pointer"
      }
    },
    (0, import_react3.createElement)(
      "div",
      { style: { display: "flex", alignItems: "center", gap: 8, width: "100%" } },
      props.icon,
      (0, import_react3.createElement)("span", { style: { fontFamily: T.mono, fontSize: 11, color: T.textDim } }, props.eyebrow),
      (0, import_react3.createElement)(
        "span",
        {
          style: {
            flex: "1 1 auto",
            fontSize: 13,
            fontWeight: 500,
            color: props.claimed ? T.text1 : T.text2,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap"
          }
        },
        props.title
      ),
      (0, import_react3.createElement)("span", { style: { flex: "0 0 auto", fontSize: 11, color: props.tagColor } }, props.tag),
      chevron()
    ),
    (0, import_react3.createElement)("div", { style: { ...HINT, fontSize: 11.5, minHeight: 34 } }, props.summary)
  );
}
function chevron() {
  return (0, import_react3.createElement)(
    "svg",
    {
      width: 12,
      height: 12,
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.5,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": true,
      style: { flex: "0 0 auto", color: T.textDim }
    },
    (0, import_react3.createElement)("path", { d: "M6.2 3.6 10.6 8l-4.4 4.4" })
  );
}
function hostGlyph() {
  return (0, import_react3.createElement)(
    "svg",
    {
      width: 14,
      height: 14,
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.3,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": true,
      style: { flex: "0 0 auto", color: T.text3 }
    },
    (0, import_react3.createElement)("path", { d: "M8 2.2 14 5.4 8 8.6 2 5.4z" }),
    (0, import_react3.createElement)("path", { d: "M2.6 8.4 8 11.3l5.4-2.9" }),
    (0, import_react3.createElement)("path", { d: "M2.6 11.2 8 14.1l5.4-2.9" })
  );
}

// src/client/history.ts
var MAX_DEPTH = 50;
function createHistoryStore(initial) {
  const store = createValueStore({ stack: [initial], cursor: 0 });
  const step = (delta) => {
    const state = store.get();
    const cursor = state.cursor + delta;
    if (cursor < 0 || cursor >= state.stack.length) return;
    store.set({ stack: state.stack, cursor });
  };
  return {
    get: store.get,
    set: store.set,
    subscribe: store.subscribe,
    current: () => {
      const state = store.get();
      return state.stack[state.cursor] ?? initial;
    },
    push(viewId) {
      const state = store.get();
      if (state.stack[state.cursor] === viewId) return;
      const kept = state.stack.slice(0, state.cursor + 1);
      kept.push(viewId);
      const overflow = Math.max(0, kept.length - MAX_DEPTH);
      const stack = overflow > 0 ? kept.slice(overflow) : kept;
      store.set({ stack, cursor: stack.length - 1 });
    },
    back: () => step(-1),
    forward: () => step(1),
    canBack: () => store.get().cursor > 0,
    canForward: () => {
      const state = store.get();
      return state.cursor < state.stack.length - 1;
    },
    reset(viewId) {
      store.set({ stack: [viewId], cursor: 0 });
    }
  };
}

// src/client/HostView.ts
var import_react4 = require("react");
function createHostView(face, t) {
  return function HostView() {
    const state = useStoreValue(face.inventory);
    const entries = state.entries;
    const counts = {
      total: entries.length,
      active: entries.filter((e) => e.fiberPhase === "active").length,
      failed: entries.filter((e) => e.fiberPhase === "failed").length,
      disabled: entries.filter((e) => !e.enabled).length
    };
    const sorted = [...entries].sort((a, b) => rank(a) - rank(b) || a.moduleName.localeCompare(b.moduleName));
    return (0, import_react4.createElement)(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: 14, maxWidth: 880 } },
      statusStrip(t, state, counts, () => {
        void face.inventory.refresh();
      }),
      pluginList(t, state, sorted)
    );
  };
}
function rank(entry) {
  if (entry.fiberPhase === "failed") return 0;
  if (entry.fiberPhase === "active") return 1;
  return 2;
}
function pluginList(t, state, entries) {
  if (state.status === "error") return notice(state.error || t("error"), T.danger);
  if (entries.length === 0 && state.status === "loading") return notice(t("loading"), T.text3);
  if (entries.length === 0) return notice(t("empty"), T.text3);
  return (0, import_react4.createElement)("div", { "data-plugin-list": "" }, ...entries.map((entry) => pluginRow(t, entry)));
}
function pluginRow(t, entry) {
  const phase = entry.fiberPhase === null ? "none" : String(entry.fiberPhase);
  return (0, import_react4.createElement)(
    "div",
    {
      key: entry.entryId,
      "data-plugin": entry.entryId,
      style: {
        display: "flex",
        alignItems: "baseline",
        gap: 8,
        padding: "6px 0",
        borderBottom: `1px solid ${T.border1}`
      }
    },
    (0, import_react4.createElement)(
      "div",
      { style: { flex: "1 1 auto", minWidth: 0 } },
      (0, import_react4.createElement)(
        "div",
        {
          style: {
            ...CODE,
            wordBreak: "break-all",
            color: entry.enabled ? T.text1 : T.text3
          }
        },
        entry.moduleName
      ),
      (0, import_react4.createElement)("div", { style: { color: T.textDim, fontSize: 11, wordBreak: "break-all" } }, entry.entryId)
    ),
    entry.enabled ? null : (0, import_react4.createElement)(
      "span",
      {
        style: {
          flex: "0 0 auto",
          fontSize: 11,
          color: T.text3,
          border: `1px solid ${T.border2}`,
          borderRadius: 4,
          padding: "0 4px"
        }
      },
      t("stat.disabled")
    ),
    (0, import_react4.createElement)(
      "span",
      { style: { flex: "0 0 auto", fontSize: 11, color: phaseColor(phase), whiteSpace: "nowrap" } },
      t(`phase.${phase}`)
    )
  );
}

// src/client/projects/jobRadar.ts
var import_react5 = require("react");
var JOB_RADAR_ID = "job-radar";
var PAGE = 25;
var GRADES = ["S", "A", "B", "C"];
var STATUSES = ["new", "applied", "interested", "rejected"];
var STATUS_LABEL = {
  new: "\u65B0\u53D1\u73B0",
  applied: "\u5DF2\u6295\u9012",
  interested: "\u6709\u610F\u5411",
  rejected: "\u5DF2\u653E\u5F03"
};
function gradeColor(grade) {
  switch (grade) {
    case "S":
      return T.ok;
    case "A":
      return T.brand;
    case "B":
      return T.warn;
    case "C":
      return T.text3;
    default:
      return T.textDim;
  }
}
function statusColor(status) {
  switch (status) {
    case "applied":
      return T.ok;
    case "interested":
      return T.warn;
    case "rejected":
      return T.textDim;
    default:
      return T.info;
  }
}
var jobRadarProject = {
  id: JOB_RADAR_ID,
  title: () => "Job Radar",
  summary: () => "\u5C97\u4F4D\u770B\u677F \xB7 \u8BFB job-radar \u5FEB\u7167\uFF0C\u53EF\u76F4\u63A5\u6807\u8BB0\u72B6\u6001",
  icon: () => radarGlyph(),
  // `render` 由工作台直接调用，不能自己持有 hook 状态；所以它只把上下文
  // 交给一个真正的组件去渲染。
  render: (ctx) => (0, import_react5.createElement)(JobRadarView, { ctx })
};
function JobRadarView(props) {
  const { ctx } = props;
  const [load, setLoad] = (0, import_react5.useState)({ status: "idle", jobs: [], readAt: 0, error: "" });
  const [gradeFilter, setGradeFilter] = (0, import_react5.useState)("");
  const [statusFilter, setStatusFilter] = (0, import_react5.useState)("");
  const [shown, setShown] = (0, import_react5.useState)(PAGE);
  const [pending, setPending] = (0, import_react5.useState)("");
  const [nonce, setNonce] = (0, import_react5.useState)(0);
  (0, import_react5.useEffect)(() => {
    let live = true;
    const face = ctx.jobRadar();
    if (face === void 0) {
      setLoad({ status: "missing", jobs: [], readAt: 0, error: "" });
      return () => {
        live = false;
      };
    }
    setLoad((prev) => ({ ...prev, status: "loading" }));
    face.list().then((res) => {
      if (!live) return;
      setLoad({ status: "ready", jobs: res?.jobs ?? [], readAt: Date.now(), error: "" });
    }).catch((err) => {
      if (live) setLoad({ status: "error", jobs: [], readAt: 0, error: message(err) });
    });
    return () => {
      live = false;
    };
  }, [nonce]);
  const jobs = load.jobs;
  const gradeCount = tally(jobs, (j) => j.grade);
  const statusCount = tally(jobs, (j) => j.status);
  const filtered = jobs.filter((j) => (gradeFilter === "" || j.grade === gradeFilter) && (statusFilter === "" || j.status === statusFilter));
  const visible = filtered.slice(0, shown);
  const mark = (id, next) => {
    const face = ctx.jobRadar();
    if (face === void 0) return;
    const key = String(id);
    setPending(key);
    face.setStatus(key, next).then((res) => {
      if (!res?.ok) {
        setLoad((prev) => ({ ...prev, error: `\u6807\u8BB0\u5931\u8D25\uFF1A${res?.error ?? "\u672A\u77E5\u539F\u56E0"}` }));
        return;
      }
      setLoad((prev) => ({
        ...prev,
        error: "",
        jobs: prev.jobs.map((j) => String(j.id) === key ? { ...j, status: next } : j)
      }));
    }).catch((err) => {
      setLoad((prev) => ({ ...prev, error: `\u6807\u8BB0\u5931\u8D25\uFF1A${message(err)}` }));
    }).finally(() => {
      setPending("");
    });
  };
  if (load.status === "missing") return sourceMissing();
  if (load.status === "error") return sourceError(load.error, () => {
    setNonce(nonce + 1);
  });
  return (0, import_react5.createElement)(
    "div",
    { style: { display: "flex", flexDirection: "column", gap: 18, maxWidth: 880 } },
    toolbar(load, jobRadarProject.title(), () => {
      setNonce(nonce + 1);
    }),
    // A refused write or a failed re-read leaves the list on screen untouched,
    // so the reason has to be shown next to it — not swallowed.
    load.error === "" ? null : (0, import_react5.createElement)(
      "div",
      {
        "data-job-error": "yes",
        style: {
          padding: "8px 10px",
          borderRadius: 8,
          border: `1px solid ${T.border2}`,
          borderLeft: `3px solid ${T.danger}`,
          background: T.bgLayer1,
          color: T.danger,
          fontSize: 12,
          wordBreak: "break-word"
        }
      },
      load.error
    ),
    filterRow(gradeFilter, setGradeFilter, statusFilter, setStatusFilter, gradeCount, statusCount, jobs.length),
    list(visible, filtered.length, shown, setShown, pending, mark)
  );
}
function toolbar(load, title, onRefresh) {
  const jobs = load.jobs;
  const cells = [
    ["\u603B\u6570", jobs.length],
    ...GRADES.map((g) => [`${g} \u7EA7`, jobs.filter((j) => j.grade === g).length]),
    ["\u5DF2\u6295\u9012", jobs.filter((j) => j.status === "applied").length]
  ];
  const newest = newestDate(jobs);
  return (0, import_react5.createElement)(
    "section",
    null,
    (0, import_react5.createElement)(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 10,
          paddingBottom: 6,
          borderBottom: `1px solid ${T.border1}`
        }
      },
      (0, import_react5.createElement)("span", { style: { ...SECTION_TITLE, flex: "1 1 auto" } }, title),
      (0, import_react5.createElement)(
        "span",
        { style: { ...CODE, color: T.textDim } },
        "remote.jobRadar"
      ),
      (0, import_react5.createElement)(
        "span",
        { style: HINT, "data-read-at": String(load.readAt) },
        load.status === "loading" && load.readAt === 0 ? "\u6B63\u5728\u8BFB\u53D6\u2026" : `\u8BFB\u53D6\u4E8E ${new Date(load.readAt).toLocaleTimeString()}`
      ),
      (0, import_react5.createElement)("button", { type: "button", onClick: onRefresh, style: OUTLINE_BUTTON }, "\u5237\u65B0")
    ),
    (0, import_react5.createElement)(
      "div",
      { style: { display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: 8, marginTop: 12 } },
      ...cells.map(([label, value]) => (0, import_react5.createElement)(
        "div",
        {
          key: label,
          style: { padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border1}`, background: T.bgLayer1 }
        },
        (0, import_react5.createElement)("div", { style: { fontSize: 11, color: T.text3 } }, label),
        (0, import_react5.createElement)("div", { style: { fontSize: 20, fontWeight: 500, lineHeight: 1.5, color: T.text1 } }, String(value))
      ))
    ),
    (0, import_react5.createElement)(
      "div",
      { style: { ...HINT, marginTop: 8 } },
      newest === "" ? "\u5FEB\u7167\u91CC\u6CA1\u6709\u4EFB\u4F55\u5E26\u65E5\u671F\u7684\u5C97\u4F4D\u3002" : `\u5FEB\u7167\u91CC\u6700\u65B0\u7684\u5C97\u4F4D\u662F ${newest}\u3002\u8FD9\u662F jobs.json \u7684\u5BFC\u51FA\u65F6\u95F4\uFF0C\u4E0D\u662F\u6293\u53D6\u65F6\u95F4 \u2014\u2014 \u6570\u5B57\u505C\u4F4F\u4E0D\u52A8\u8BF4\u660E\u8BE5\u8DD1\u4E00\u6B21 job-radar \u6293\u53D6\u4E86\u3002`
    )
  );
}
function filterRow(gradeFilter, setGrade, statusFilter, setStatus, gradeCount, statusCount, total) {
  return (0, import_react5.createElement)(
    "section",
    { style: { display: "flex", flexDirection: "column", gap: 6 } },
    (0, import_react5.createElement)(
      "div",
      { style: { display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" } },
      (0, import_react5.createElement)("span", { style: { ...SECTION_TITLE, width: 34 } }, "\u7B49\u7EA7"),
      chip("\u5168\u90E8", total, gradeFilter === "", T.text1, () => setGrade("")),
      ...GRADES.map((g) => chip(g, gradeCount[g] ?? 0, gradeFilter === g, gradeColor(g), () => setGrade(g)))
    ),
    (0, import_react5.createElement)(
      "div",
      { style: { display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" } },
      (0, import_react5.createElement)("span", { style: { ...SECTION_TITLE, width: 34 } }, "\u72B6\u6001"),
      chip("\u5168\u90E8", total, statusFilter === "", T.text1, () => setStatus("")),
      ...STATUSES.map((s) => chip(
        STATUS_LABEL[s] ?? s,
        statusCount[s] ?? 0,
        statusFilter === s,
        statusColor(s),
        () => setStatus(s)
      ))
    )
  );
}
function chip(label, count, active, color, onClick) {
  return (0, import_react5.createElement)(
    "button",
    {
      key: label,
      type: "button",
      "data-chip": label,
      "data-active": active ? "yes" : "no",
      "data-count": String(count),
      onClick,
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 9px",
        borderRadius: 999,
        border: `1px solid ${active ? color : T.border2}`,
        background: active ? T.bgHover : "transparent",
        color: active ? color : T.text2,
        font: "inherit",
        fontSize: 12,
        cursor: "pointer"
      }
    },
    (0, import_react5.createElement)("span", null, label),
    (0, import_react5.createElement)("span", { style: { color: T.textDim, fontFamily: T.mono, fontSize: 11 } }, String(count))
  );
}
function list(visible, matched, shown, setShown, pending, mark) {
  if (visible.length === 0) {
    return (0, import_react5.createElement)(
      "div",
      { style: { padding: "24px 0", color: T.text3, fontSize: 12 } },
      matched === 0 ? "\u5F53\u524D\u7B5B\u9009\u4E0B\u6CA1\u6709\u5C97\u4F4D\u3002" : "\u6CA1\u6709\u53EF\u663E\u793A\u7684\u5C97\u4F4D\u3002"
    );
  }
  return (0, import_react5.createElement)(
    "section",
    { style: { display: "flex", flexDirection: "column" } },
    ...visible.map((job) => row(job, pending, mark)),
    matched > visible.length ? (0, import_react5.createElement)(
      "button",
      {
        type: "button",
        onClick: () => setShown(Number.MAX_SAFE_INTEGER),
        style: { ...OUTLINE_BUTTON, alignSelf: "flex-start", marginTop: 12 }
      },
      `\u8FD8\u6709 ${matched - visible.length} \u6761\uFF0C\u5168\u90E8\u5C55\u5F00`
    ) : null
  );
}
function row(job, pending, mark) {
  const key = String(job.id);
  const details = job.details;
  const hits = details?.skill_hits ?? [];
  const busy = pending === key;
  return (0, import_react5.createElement)(
    "div",
    {
      key,
      "data-job": key,
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 5,
        padding: "10px 0 12px",
        borderBottom: `1px solid ${T.border1}`
      }
    },
    // 标题行
    (0, import_react5.createElement)(
      "div",
      { style: { display: "flex", alignItems: "baseline", gap: 8 } },
      (0, import_react5.createElement)(
        "span",
        {
          style: {
            flex: "0 0 auto",
            minWidth: 20,
            textAlign: "center",
            borderRadius: 5,
            padding: "0 5px",
            fontFamily: T.mono,
            fontSize: 11,
            fontWeight: 700,
            lineHeight: "17px",
            color: T.bgBase,
            background: gradeColor(job.grade)
          }
        },
        job.grade ?? "?"
      ),
      (0, import_react5.createElement)(
        "span",
        { style: { flex: "1 1 auto", fontSize: 13.5, fontWeight: 500, color: T.text1, minWidth: 0 } },
        job.title || "(\u65E0\u6807\u9898)",
        job.url ? (0, import_react5.createElement)(
          "a",
          {
            href: job.url,
            target: "_blank",
            rel: "noreferrer",
            style: { marginLeft: 8, fontSize: 12, color: T.brand, textDecoration: "none" }
          },
          "\u6253\u5F00 \u2197"
        ) : null
      ),
      (0, import_react5.createElement)(
        "span",
        { style: { flex: "0 0 auto", fontFamily: T.mono, fontSize: 12, color: T.text2 } },
        String(job.score ?? 0)
      ),
      (0, import_react5.createElement)(
        "span",
        { style: { flex: "0 0 auto", fontSize: 11, color: statusColor(job.status) } },
        STATUS_LABEL[job.status ?? ""] ?? job.status ?? ""
      )
    ),
    // 元信息行
    (0, import_react5.createElement)(
      "div",
      { style: { ...HINT, paddingLeft: 28 } },
      [job.company || "-", job.city || "-", salaryText(job), experienceText(job), job.education || ""].filter((part) => part !== "").join(" \xB7 ")
    ),
    // 评分明细：回答"这条为什么是 A 级"
    details ? (0, import_react5.createElement)(
      "div",
      { style: { ...CODE, paddingLeft: 28, color: T.text3 } },
      `\u6280\u80FD ${details.skill ?? 0} \xB7 \u7ECF\u9A8C ${details.experience ?? 0} \xB7 \u516C\u53F8 ${details.company ?? 0} \xB7 \u65B0\u9C9C ${details.freshness ?? 0} \xB7 \u901A\u52E4 ${details.commute ?? 0}`
    ) : null,
    hits.length > 0 ? (0, import_react5.createElement)(
      "div",
      { style: { display: "flex", flexWrap: "wrap", gap: 4, paddingLeft: 28 } },
      ...hits.slice(0, 6).map((hit) => (0, import_react5.createElement)(
        "span",
        {
          key: hit,
          style: {
            fontSize: 11,
            color: T.text2,
            background: T.bgLayer2,
            borderRadius: 4,
            padding: "1px 5px"
          }
        },
        hit
      )),
      hits.length > 6 ? (0, import_react5.createElement)("span", { style: { fontSize: 11, color: T.textDim } }, `+${hits.length - 6}`) : null
    ) : null,
    // 状态标记
    (0, import_react5.createElement)(
      "div",
      { style: { display: "flex", gap: 6, paddingLeft: 28, marginTop: 2 } },
      ...STATUSES.map((s) => (0, import_react5.createElement)(
        "button",
        {
          key: s,
          type: "button",
          "data-mark": `${key}:${s}`,
          disabled: busy,
          onClick: () => mark(job.id, s),
          style: {
            ...OUTLINE_BUTTON,
            fontSize: 11,
            padding: "1px 7px",
            borderColor: job.status === s ? statusColor(s) : T.border1,
            color: job.status === s ? statusColor(s) : T.text3,
            opacity: busy ? 0.5 : 1,
            cursor: busy ? "default" : "pointer"
          }
        },
        STATUS_LABEL[s]
      ))
    )
  );
}
function sourceMissing() {
  return (0, import_react5.createElement)(
    "div",
    {
      "data-job-source": "missing",
      style: {
        maxWidth: 620,
        margin: "16px auto 0",
        padding: "18px 20px",
        border: `1px dashed ${T.border2}`,
        borderRadius: 12,
        background: T.bgLayer1
      }
    },
    (0, import_react5.createElement)("div", { style: { fontSize: 13, fontWeight: 500, color: T.text1 } }, "Job Radar \u6570\u636E\u6E90\u672A\u88C5\u8F7D"),
    (0, import_react5.createElement)(
      "div",
      { style: { ...HINT, marginTop: 8 } },
      "\u8FD9\u4E2A\u9879\u76EE\u81EA\u5DF1\u4E0D\u8BFB\u6587\u4EF6 \u2014\u2014 \u5C97\u4F4D\u6570\u636E\u7531 dsh-job-radar \u63D2\u4EF6\u901A\u8FC7 remote.jobRadar \u63D0\u4F9B\u3002\u5F53\u524D profile \u91CC\u6CA1\u6709\u89E3\u6790\u5230\u8FD9\u4E2A\u6570\u636E\u9762\uFF0C\u6240\u4EE5\u8FD9\u91CC\u5148\u7A7A\u7740\u3002"
    ),
    (0, import_react5.createElement)(
      "div",
      { style: { ...HINT, marginTop: 8 } },
      "\u8981\u5728\u5DE5\u4F5C\u53F0\u91CC\u770B\u5230\u5C97\u4F4D\uFF0C\u628A dsh-job-radar \u88C5\u8FDB\u540C\u4E00\u4E2A profile \u5E76\u7ED9\u5B83\u914D\u597D dataDir\uFF08\u6307\u5411 job-radar \u7684 data \u76EE\u5F55\uFF09\uFF0C\u7136\u540E\u91CD\u542F\u5BBF\u4E3B\uFF1A"
    ),
    (0, import_react5.createElement)(
      "div",
      {
        style: {
          ...CODE,
          marginTop: 8,
          padding: "8px 10px",
          borderRadius: 8,
          background: T.bgLayer2,
          border: `1px solid ${T.border1}`,
          wordBreak: "break-all"
        }
      },
      'dsh plugin --profile <profile> add "file:<job-radar>/plugin/dsh-job-radar"'
    ),
    (0, import_react5.createElement)(
      "div",
      { style: { ...HINT, marginTop: 8, color: T.textDim } },
      "\u6CE8\u610F\uFF1A\u8FD9\u4E2A\u4F9D\u8D56\u662F\u523B\u610F\u505A\u6210\u53EF\u9009\u7684 \u2014\u2014 \u5DE5\u4F5C\u53F0\u7684\u5176\u4F59\u90E8\u5206\u5728\u5B83\u7F3A\u5E2D\u65F6\u7167\u5E38\u5DE5\u4F5C\u3002"
    )
  );
}
function sourceError(error, onRetry) {
  return (0, import_react5.createElement)(
    "div",
    {
      "data-job-source": "error",
      style: {
        maxWidth: 620,
        margin: "16px auto 0",
        padding: "14px 16px",
        border: `1px solid ${T.border2}`,
        borderLeft: `3px solid ${T.danger}`,
        borderRadius: 10,
        background: T.bgLayer1
      }
    },
    (0, import_react5.createElement)("div", { style: { fontSize: 13, fontWeight: 500, color: T.danger } }, "\u8BFB\u53D6\u5C97\u4F4D\u6570\u636E\u5931\u8D25"),
    (0, import_react5.createElement)("div", { style: { ...CODE, marginTop: 6, color: T.text2, wordBreak: "break-word" } }, error),
    (0, import_react5.createElement)(
      "button",
      { type: "button", onClick: onRetry, style: { ...OUTLINE_BUTTON, marginTop: 10 } },
      "\u91CD\u8BD5"
    )
  );
}
function radarGlyph() {
  return (0, import_react5.createElement)(
    "svg",
    {
      width: 14,
      height: 14,
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.3,
      strokeLinecap: "round",
      "aria-hidden": true,
      style: { flex: "0 0 auto" }
    },
    (0, import_react5.createElement)("circle", { cx: 8, cy: 8, r: 5.6 }),
    (0, import_react5.createElement)("circle", { cx: 8, cy: 8, r: 1.1, fill: "currentColor", stroke: "none" }),
    (0, import_react5.createElement)("path", { d: "M8 8l4.2-5.4" })
  );
}
function message(err) {
  return err instanceof Error ? err.message : String(err);
}
function tally(jobs, pick) {
  const out = {};
  for (const job of jobs) {
    const key = pick(job);
    if (key === void 0 || key === "") continue;
    out[key] = (out[key] ?? 0) + 1;
  }
  return out;
}
function salaryText(job) {
  const k = (value) => `${Math.round(value / 1e3)}K`;
  if (job.salary_min && job.salary_max) return `${k(job.salary_min)}-${k(job.salary_max)}`;
  if (job.salary_min) return `${k(job.salary_min)}+`;
  if (job.salary_max) return `\u2264${k(job.salary_max)}`;
  return "\u9762\u8BAE";
}
function experienceText(job) {
  if (job.experience_min !== void 0 && job.experience_max !== void 0) {
    return `${job.experience_min}-${job.experience_max} \u5E74`;
  }
  if (job.experience_min !== void 0) return `${job.experience_min} \u5E74\u4EE5\u4E0A`;
  return "";
}
function newestDate(jobs) {
  let newest = 0;
  for (const job of jobs) {
    const at = job.created_at ? Date.parse(job.created_at) : NaN;
    if (!Number.isNaN(at) && at > newest) newest = at;
  }
  return newest === 0 ? "" : new Date(newest).toLocaleDateString();
}

// src/client/projects/host.ts
var import_react6 = require("react");
var SNIPPET = [
  "{",
  "  id: 'my-project',",
  "  title: () => '\u6211\u7684\u9879\u76EE',",
  "  render: (ctx) => h('div', null, '\u5185\u5BB9'),",
  "}"
].join("\n");
function createProjectHost(projectCtx, t) {
  return function ProjectHost(props) {
    const { slot, index } = props;
    if (slot === null || slot === void 0) return placeholder(index, t);
    let body2;
    try {
      body2 = slot.render(projectCtx);
    } catch (err) {
      body2 = failure(index, err, t);
    }
    return (0, import_react6.createElement)("div", { style: { minHeight: "100%" } }, body2);
  };
}
function placeholder(index, t) {
  return (0, import_react6.createElement)(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 12,
        maxWidth: 520,
        margin: "24px auto 0",
        padding: "20px 22px",
        border: `1px dashed ${T.border2}`,
        borderRadius: 12,
        background: T.bgLayer1
      }
    },
    (0, import_react6.createElement)(
      "div",
      { style: { display: "flex", alignItems: "baseline", gap: 10 } },
      (0, import_react6.createElement)(
        "span",
        {
          style: {
            fontFamily: T.mono,
            fontSize: 26,
            fontWeight: 600,
            lineHeight: 1,
            color: T.textDim
          }
        },
        pad2(index + 1)
      ),
      (0, import_react6.createElement)("span", { style: { fontSize: 14, fontWeight: 500, color: T.text1 } }, slotLabel(index, t)),
      (0, import_react6.createElement)(
        "span",
        {
          style: {
            fontSize: 11,
            color: T.text3,
            border: `1px solid ${T.border2}`,
            borderRadius: 4,
            padding: "1px 5px"
          }
        },
        t("slot.free")
      )
    ),
    (0, import_react6.createElement)("div", { style: HINT }, t("slot.free.hint")),
    (0, import_react6.createElement)(
      "div",
      { style: { display: "flex", alignItems: "baseline", gap: 8, fontSize: 12 } },
      (0, import_react6.createElement)("span", { style: { color: T.text3 } }, t("slot.free.file")),
      (0, import_react6.createElement)("code", { style: { ...CODE, color: T.brand } }, "src/client/projects/slots.ts")
    ),
    (0, import_react6.createElement)(
      "pre",
      {
        style: {
          ...CODE,
          margin: 0,
          width: "100%",
          boxSizing: "border-box",
          padding: "10px 12px",
          borderRadius: 8,
          background: T.bgLayer2,
          border: `1px solid ${T.border1}`,
          whiteSpace: "pre",
          overflowX: "auto"
        }
      },
      SNIPPET
    )
  );
}
function failure(index, err, t) {
  const message2 = err instanceof Error ? err.message : String(err);
  return (0, import_react6.createElement)(
    "div",
    {
      style: {
        maxWidth: 560,
        padding: "14px 16px",
        border: `1px solid ${T.border2}`,
        borderLeft: `3px solid ${T.danger}`,
        borderRadius: 10,
        background: T.bgLayer1
      }
    },
    (0, import_react6.createElement)(
      "div",
      { style: { fontSize: 13, fontWeight: 500, color: T.danger } },
      `${slotLabel(index, t)} \xB7 ${t("slot.error")}`
    ),
    (0, import_react6.createElement)("div", { style: { ...CODE, marginTop: 6, color: T.text2, wordBreak: "break-word" } }, message2)
  );
}

// src/client/projects/jobRadarRemote.ts
async function unwrap(call, method) {
  const result = await call;
  if (result === null || typeof result !== "object" || result.ok !== true) {
    throw new Error(result?.error?.message ?? `jobRadar.${method} \u8C03\u7528\u5931\u8D25`);
  }
  return result.value;
}
function toJobRadarFace(raw) {
  if (raw === null || typeof raw !== "object") return void 0;
  const ns = raw;
  if (typeof ns.list !== "function" || typeof ns.stats !== "function" || typeof ns.setStatus !== "function") {
    return void 0;
  }
  return {
    // `?? {}` 不是防御性冗余 —— 少了它这次调用会被网关按参数个数拒掉。
    list: (filter) => unwrap(ns.list(filter ?? {}), "list"),
    stats: () => unwrap(ns.stats(), "stats"),
    setStatus: (id, status) => unwrap(ns.setStatus(id, status), "setStatus")
  };
}

// src/client/projects/slots.ts
var PROJECT_SLOTS = [
  jobRadarProject,
  // 项目 01 —— Job Radar 岗位看板
  null,
  // 项目 02 —— 预留
  null,
  // 项目 03 —— 预留
  null
  // 项目 04 —— 预留
];

// src/client/Trigger.ts
var import_react7 = require("react");
function createTrigger(face, t) {
  return function Trigger(props) {
    const shown = useStoreValue(face.shown);
    const entries = useStoreValue(face.inventory).entries;
    const wide = props?.wide === true;
    const failed = entries.filter((e) => e.fiberPhase === "failed").length;
    return (0, import_react7.createElement)(
      "button",
      {
        type: "button",
        title: t("action"),
        "aria-label": t("action"),
        "aria-current": shown ? "page" : void 0,
        "aria-pressed": shown ? "true" : "false",
        onClick: () => face.toggle(!shown),
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          width: wide ? "100%" : 32,
          height: 32,
          padding: wide ? "0 8px" : 0,
          justifyContent: wide ? "flex-start" : "center",
          border: "1px solid transparent",
          borderRadius: 8,
          // Selected reads like the other sidebar panel rows do: a filled
          // surface, not just a colour change.
          background: shown ? T.bgHover : "transparent",
          color: failed > 0 ? T.danger : shown ? T.text1 : T.text2,
          font: "inherit",
          fontSize: 13,
          cursor: "pointer"
        }
      },
      glyph(16),
      wide ? (0, import_react7.createElement)("span", { style: { flex: "1 1 auto", textAlign: "left" } }, t("action")) : null,
      failed > 0 ? (0, import_react7.createElement)(
        "span",
        {
          style: {
            flex: "0 0 auto",
            minWidth: 18,
            height: 18,
            padding: "0 5px",
            boxSizing: "border-box",
            borderRadius: 9,
            background: T.bgHover,
            color: T.danger,
            fontSize: 11,
            lineHeight: "18px",
            textAlign: "center"
          }
        },
        String(failed)
      ) : null
    );
  };
}
function glyph(size) {
  return (0, import_react7.createElement)(
    "svg",
    {
      width: size,
      height: size,
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.3,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": true,
      style: { flex: "0 0 auto" }
    },
    (0, import_react7.createElement)("rect", { x: 1.6, y: 2.6, width: 12.8, height: 10.8, rx: 1.6 }),
    (0, import_react7.createElement)("path", { d: "M6.2 2.9v10.2" }),
    (0, import_react7.createElement)("path", { d: "M8.2 6.1h4.2" }),
    (0, import_react7.createElement)("path", { d: "M8.2 9.1h2.8" })
  );
}

// src/client/Workbench.ts
var import_react8 = require("react");
function createWorkbench(face, t) {
  const ProjectHost = createProjectHost(face.projectCtx, t);
  const ControlRoom = createControlRoom({
    inventory: face.projectCtx.inventory,
    projects: face.projects,
    onOpen: (id) => face.history.push(id)
  }, t);
  const HostView = createHostView({ inventory: face.projectCtx.inventory }, t);
  return function Workbench() {
    const history = useStoreValue(face.history);
    (0, import_react8.useEffect)(() => {
      face.shown.set(true);
      return () => {
        face.shown.set(false);
      };
    }, []);
    (0, import_react8.useEffect)(() => {
      void face.projectCtx.inventory.refresh();
    }, []);
    (0, import_react8.useEffect)(() => {
      const onKey = (event) => {
        if (!event.altKey) return;
        if (event.key === "ArrowLeft") face.history.back();
        else if (event.key === "ArrowRight") face.history.forward();
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, []);
    const viewId = clampViewId(history.stack[history.cursor] ?? CONTROL_ROOM_ID, face.projects.length);
    return (0, import_react8.createElement)(
      "div",
      {
        "data-workbench": "",
        "aria-label": t("title"),
        style: {
          display: "flex",
          flexDirection: "column",
          height: "100%",
          minHeight: 0,
          overflow: "hidden",
          background: T.bgBase,
          color: T.text1,
          fontFamily: T.font,
          fontSize: 13
        }
      },
      chrome(t, face, history, viewId),
      (0, import_react8.createElement)(
        "div",
        {
          // Which view is in the body, as an attribute: the headless smoke test
          // cannot see through the component boundary, and neither can you when
          // inspecting the live DOM.
          "data-view": viewId,
          style: { flex: "1 1 auto", minHeight: 0, padding: "20px 24px 28px", ...SCROLL }
        },
        body(viewId, face, { ControlRoom, HostView, ProjectHost })
      )
    );
  };
}
function body(viewId, face, views) {
  if (viewId === HOST_ID) return (0, import_react8.createElement)(views.HostView, { key: HOST_ID });
  const index = slotIndexOf(viewId);
  if (index === null) return (0, import_react8.createElement)(views.ControlRoom, { key: CONTROL_ROOM_ID });
  return (0, import_react8.createElement)(views.ProjectHost, {
    key: slotViewId(index),
    slot: face.projects[index] ?? null,
    index
  });
}
function viewTitle(t, face, viewId) {
  if (viewId === HOST_ID) return t("host");
  const index = slotIndexOf(viewId);
  if (index === null) return t("console");
  const slot = face.projects[index];
  return slot !== null && slot !== void 0 ? slot.title() : slotLabel(index, t);
}
function chrome(t, face, history, viewId) {
  const atConsole = viewId === CONTROL_ROOM_ID;
  return (0, import_react8.createElement)(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "9px 14px",
        borderBottom: `1px solid ${T.border1}`,
        flex: "0 0 auto"
      }
    },
    navButton("back", t("back"), history.cursor > 0, () => face.history.back(), arrow("M10.4 3.2 5.6 8l4.8 4.8")),
    navButton(
      "forward",
      t("forward"),
      history.cursor < history.stack.length - 1,
      () => face.history.forward(),
      arrow("M5.6 3.2 10.4 8l-4.8 4.8")
    ),
    (0, import_react8.createElement)("span", { style: { width: 1, height: 18, background: T.border1, margin: "0 6px" } }),
    atConsole ? crumb(t("console"), CONTROL_ROOM_ID, null) : crumb(t("console"), CONTROL_ROOM_ID, () => face.history.push(CONTROL_ROOM_ID)),
    atConsole ? null : crumbSeparator(),
    atConsole ? null : crumb(viewTitle(t, face, viewId), viewId, null),
    (0, import_react8.createElement)("span", { style: { flex: "1 1 auto" } }),
    (0, import_react8.createElement)(
      "button",
      { type: "button", title: t("exit"), onClick: () => face.close(), style: OUTLINE_BUTTON },
      t("exit")
    )
  );
}
function crumb(label, viewId, onSelect) {
  return (0, import_react8.createElement)(
    "button",
    {
      key: viewId,
      type: "button",
      "data-crumb": viewId,
      "aria-current": onSelect === null ? "page" : void 0,
      onClick: onSelect ?? void 0,
      style: {
        border: "1px solid transparent",
        borderRadius: 6,
        background: "transparent",
        color: onSelect === null ? T.text1 : T.text2,
        font: "inherit",
        fontSize: 12.5,
        fontWeight: onSelect === null ? 500 : 400,
        padding: "2px 6px",
        cursor: onSelect === null ? "default" : "pointer"
      }
    },
    label
  );
}
function crumbSeparator() {
  return (0, import_react8.createElement)(
    "span",
    { key: "sep", style: { color: T.textDim, fontSize: 11, userSelect: "none" } },
    "\u203A"
  );
}
function navButton(id, label, enabled, onClick, glyph2) {
  return (0, import_react8.createElement)(
    "button",
    {
      type: "button",
      "data-nav": id,
      title: label,
      "aria-label": label,
      "aria-disabled": enabled ? void 0 : "true",
      disabled: !enabled,
      onClick,
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 26,
        height: 26,
        border: "1px solid transparent",
        borderRadius: 6,
        background: "transparent",
        color: enabled ? T.text2 : T.textDim,
        font: "inherit",
        padding: 0,
        cursor: enabled ? "pointer" : "default"
      }
    },
    glyph2
  );
}
function arrow(d) {
  return (0, import_react8.createElement)(
    "svg",
    {
      width: 15,
      height: 15,
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.5,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": true
    },
    (0, import_react8.createElement)("path", { d })
  );
}

// src/client/index.ts
var NS = "dsh-plugin-workbench";
function resolveOptionalRemote(ctx, name2) {
  return ctx.reflect?.get(name2);
}
function resolveLayout(ctx) {
  return ctx.reflect?.get("layout");
}
var name = "dsh-plugin-workbench";
var inject = ["slots", "locale", "remote", "remote.pluginInventory"];
function apply(ctx) {
  ctx.effect(
    () => ctx.locale.register(NS, { zh: DICT_ZH, en: DICT_EN }),
    "dsh-plugin-workbench: dictionaries"
  );
  const t = ctx.locale.bind(NS);
  const shown = createValueStore(false);
  const history = createHistoryStore(CONTROL_ROOM_ID);
  const inventory = createInventoryStore(async () => {
    const result = await ctx.remote.pluginInventory.list();
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error?.code}: ${result.error?.message}`);
    }
    return result.value?.entries ?? [];
  });
  const select = (panelId) => {
    const layout = resolveLayout(ctx);
    if (layout === void 0) return;
    try {
      layout.selectPanel(panelId);
    } catch {
    }
  };
  const projectCtx = {
    t,
    inventory,
    // Adapter, not a cast: the mounted namespace speaks the gateway's envelope
    // and enforces parameter arity, while `JobRadarFace` promises neither.
    // See `projects/jobRadarRemote.ts`.
    jobRadar: () => toJobRadarFace(resolveOptionalRemote(ctx, "remote.jobRadar"))
  };
  void inventory.refresh();
  ctx.slots.inject("sidebar.footer.action", () => ctx.slots.register({
    name: "sidebar.footer.action",
    id: PANEL_ID,
    order: 60,
    label: () => t("action")
  }, createTrigger({ shown, inventory, toggle: (show) => select(show ? PANEL_ID : null) }, t)));
  try {
    ctx.slots.inject("main", () => ctx.slots.register({
      name: "main",
      key: PANEL_ID
    }, createWorkbench({
      shown,
      history,
      projects: PROJECT_SLOTS,
      projectCtx,
      close: () => select(null)
    }, t)));
  } catch {
  }
}
var DICT_ZH = {
  action: "\u5DE5\u4F5C\u53F0",
  title: "\u53EF\u89C6\u5316\u5DE5\u4F5C\u53F0",
  console: "\u63A7\u5236\u53F0",
  host: "\u5BBF\u4E3B\u63D2\u4EF6",
  "host.subtitle": "\u672C profile \u88C5\u8F7D\u7684\u63D2\u4EF6\u4E0E\u8FD0\u884C\u72B6\u6001",
  back: "\u540E\u9000\uFF08Alt + \u2190\uFF09",
  forward: "\u524D\u8FDB\uFF08Alt + \u2192\uFF09",
  exit: "\u8FD4\u56DE\u4F1A\u8BDD",
  "section.projects": "\u9879\u76EE",
  "section.host": "\u5BBF\u4E3B",
  slot: "\u9879\u76EE",
  "slot.free": "\u9884\u7559",
  "slot.filled": "\u5DF2\u63A5\u5165",
  "slot.free.summary": "\u8FD8\u6CA1\u6709\u63A5\u5165\u9879\u76EE",
  "slot.free.hint": "\u628A\u4E0B\u9762\u8FD9\u4E2A\u5BF9\u8C61\u586B\u8FDB slots.ts \u91CC\u5BF9\u5E94\u7684\u4F4D\u7F6E\uFF0C\u5B83\u5C31\u4F1A\u51FA\u73B0\u5728\u8FD9\u91CC\u3002",
  "slot.free.file": "\u8981\u6539\u7684\u6587\u4EF6",
  "slot.error": "\u6E32\u67D3\u5931\u8D25",
  "stat.total": "\u63D2\u4EF6\u603B\u6570",
  "stat.active": "\u8FD0\u884C\u4E2D",
  "stat.failed": "\u5931\u8D25",
  "stat.disabled": "\u5DF2\u7981\u7528",
  refresh: "\u91CD\u65B0\u8BFB\u53D6",
  readAt: "\u8BFB\u53D6\u4E8E",
  loading: "\u6B63\u5728\u8BFB\u53D6\u2026",
  error: "\u8BFB\u53D6\u5931\u8D25",
  empty: "\u8FD9\u4E2A profile \u6CA1\u6709\u88C5\u8F7D\u4EFB\u4F55\u63D2\u4EF6",
  "phase.pending": "\u5F85\u52A0\u8F7D",
  "phase.loading": "\u52A0\u8F7D\u4E2D",
  "phase.active": "\u8FD0\u884C\u4E2D",
  "phase.failed": "\u542F\u52A8\u5931\u8D25",
  "phase.unloading": "\u5378\u8F7D\u4E2D",
  "phase.none": "\u65E0\u5B9E\u4F8B"
};
var DICT_EN = {
  action: "Workbench",
  title: "Workbench",
  console: "Console",
  host: "Host plugins",
  "host.subtitle": "Plugins this profile composes, and how far each got",
  back: "Back (Alt + \u2190)",
  forward: "Forward (Alt + \u2192)",
  exit: "Back to chat",
  "section.projects": "Projects",
  "section.host": "Host",
  slot: "Project",
  "slot.free": "reserved",
  "slot.filled": "live",
  "slot.free.summary": "No project wired up yet",
  "slot.free.hint": "Drop the object below into the matching position in slots.ts and it shows up here.",
  "slot.free.file": "File to edit",
  "slot.error": "render failed",
  "stat.total": "plugins",
  "stat.active": "running",
  "stat.failed": "failed",
  "stat.disabled": "disabled",
  refresh: "Refresh",
  readAt: "read at",
  loading: "Reading\u2026",
  error: "Read failed",
  empty: "This profile composes no plugins",
  "phase.pending": "pending",
  "phase.loading": "loading",
  "phase.active": "running",
  "phase.failed": "failed",
  "phase.unloading": "unloading",
  "phase.none": "no fiber"
};
var __testHooks = {
  CONTROL_ROOM_ID,
  HOST_ID,
  PANEL_ID,
  JOB_RADAR_ID,
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
  jobRadarProject,
  jobRadarView: JobRadarView,
  toJobRadarFace
};
return module.exports; } });
