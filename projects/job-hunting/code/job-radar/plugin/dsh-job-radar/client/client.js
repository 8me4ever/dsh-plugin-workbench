window.__ModuleLoader__.load({ id: "dsh-job-radar", factory: (require) => {
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
  apply: () => apply,
  inject: () => inject,
  name: () => name
});
module.exports = __toCommonJS(index_exports);
var import_react2 = require("react");

// src/client/RadarPanel.ts
var import_react = require("react");
var STATUS_LABEL = {
  new: "\u65B0\u53D1\u73B0",
  applied: "\u5DF2\u6295\u9012",
  interested: "\u6709\u610F\u5411",
  rejected: "\u5DF2\u653E\u5F03"
};
var STATUS_COLOR = {
  new: "#3b82f6",
  applied: "#10b981",
  interested: "#f59e0b",
  rejected: "#ef4444"
};
var GRADE_COLOR = {
  S: "#10b981",
  A: "#3b82f6",
  B: "#f59e0b",
  C: "#94a3b8"
};
function RadarPanel({ hooks }) {
  const [jobs, setJobs] = (0, import_react.useState)([]);
  const [stats, setStats] = (0, import_react.useState)({});
  const [grade, setGrade] = (0, import_react.useState)("");
  const [status, setStatus] = (0, import_react.useState)("");
  const [loading, setLoading] = (0, import_react.useState)(true);
  const [error, setError] = (0, import_react.useState)("");
  const load = async () => {
    const remote = hooks.remote();
    if (!remote) {
      setError("Job Radar \u670D\u52A1\u672A\u6302\u8F7D(dataDir \u672A\u914D\u7F6E)");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const filter = {};
      if (grade) filter.grade = grade;
      if (status) filter.status = status;
      const [listRes, statsRes] = await Promise.all([remote.list(filter), remote.stats()]);
      setJobs(listRes.jobs);
      setStats(statsRes);
      setError("");
    } catch (e) {
      setError("\u52A0\u8F7D\u5931\u8D25: " + (e?.message ?? String(e)));
    } finally {
      setLoading(false);
    }
  };
  (0, import_react.useEffect)(() => {
    void load();
  }, [grade, status]);
  const mark = async (jid, st) => {
    const remote = hooks.remote();
    if (!remote) return;
    const res = await remote.setStatus(jid, st);
    if (res.ok) void load();
    else setError("\u6807\u8BB0\u5931\u8D25: " + (res.error ?? ""));
  };
  const grades = ["S", "A", "B", "C"];
  const statuses = Object.keys(STATUS_LABEL);
  const total = stats.total ?? 0;
  const cardStyle = {
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: "10px 14px",
    marginBottom: 8,
    background: "#fff"
  };
  const badgeStyle = (g) => ({
    display: "inline-block",
    minWidth: 22,
    textAlign: "center",
    borderRadius: 6,
    padding: "1px 6px",
    marginRight: 8,
    fontWeight: 700,
    color: "#fff",
    background: GRADE_COLOR[g] ?? "#94a3b8"
  });
  const chipStyle = (active) => ({
    border: active ? "2px solid #3b82f6" : "1px solid #cbd5e1",
    borderRadius: 999,
    padding: "2px 10px",
    marginRight: 6,
    marginBottom: 6,
    cursor: "pointer",
    background: active ? "#eff6ff" : "#fff",
    color: active ? "#1d4ed8" : "#475569",
    fontSize: 12
  });
  return (0, import_react.createElement)("div", { style: { fontFamily: "inherit" } }, [
    // Stats row
    (0, import_react.createElement)("div", { key: "stats", style: { display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" } }, [
      (0, import_react.createElement)("span", { key: "t", style: statChip("#334155") }, `\u603B\u6570 ${total}`),
      (0, import_react.createElement)("span", { key: "s", style: statChip(GRADE_COLOR.S) }, `S ${stats.grade_S ?? 0}`),
      (0, import_react.createElement)("span", { key: "a", style: statChip(GRADE_COLOR.A) }, `A ${stats.grade_A ?? 0}`),
      (0, import_react.createElement)("span", { key: "b", style: statChip(GRADE_COLOR.B) }, `B ${stats.grade_B ?? 0}`),
      (0, import_react.createElement)("span", { key: "ap", style: statChip(STATUS_COLOR.applied) }, `\u5DF2\u6295 ${stats.status_applied ?? 0}`),
      (0, import_react.createElement)("button", { key: "ref", onClick: () => void load(), style: refreshStyle() }, "\u{1F504} \u5237\u65B0")
    ]),
    // Grade filter
    (0, import_react.createElement)("div", { key: "gf" }, [
      chip("", "\u5168\u90E8\u7B49\u7EA7", grade === ""),
      ...grades.map((g) => chip(g, `${g} \u7EA7`, grade === g))
    ]),
    // Status filter
    (0, import_react.createElement)("div", { key: "sf" }, [
      chip("", "\u5168\u90E8\u72B6\u6001", status === ""),
      ...statuses.map((s) => chip(s, STATUS_LABEL[s], status === s))
    ]),
    error ? (0, import_react.createElement)("div", { key: "err", style: { color: "#dc2626", margin: "8px 0" } }, error) : null,
    loading ? (0, import_react.createElement)("div", { key: "ld", style: { color: "#64748b", margin: "16px 0" } }, "\u52A0\u8F7D\u4E2D...") : null,
    // Job cards
    (0, import_react.createElement)("div", { key: "list" }, jobs.map((j) => (0, import_react.createElement)("div", { key: j.id, style: cardStyle }, [
      (0, import_react.createElement)("div", { key: "t", style: { fontWeight: 600, fontSize: 14 } }, [
        (0, import_react.createElement)("span", { key: "b", style: badgeStyle(j.grade) }, j.grade ?? "?"),
        j.title || "(\u65E0\u6807\u9898)",
        j.url ? (0, import_react.createElement)("a", { key: "l", href: j.url, target: "_blank", style: { marginLeft: 8, fontSize: 12, color: "#3b82f6" } }, "\u{1F517}") : null
      ]),
      (0, import_react.createElement)("div", { key: "m", style: { fontSize: 12, color: "#64748b", margin: "4px 0" } }, [
        `${j.company || "-"} \xB7 ${j.city || "-"} \xB7 ${fmtSalary(j)} \xB7 \u8BC4\u5206 ${j.score ?? 0}`
      ]),
      (0, import_react.createElement)("div", { key: "a", style: { marginTop: 6 } }, [
        ...statuses.map((s) => (0, import_react.createElement)("button", {
          key: s,
          onClick: () => void mark(j.id, s),
          style: miniBtn(j.status === s, STATUS_COLOR[s])
        }, STATUS_LABEL[s]))
      ])
    ])))
  ]);
  function chip(value, label, active) {
    return (0, import_react.createElement)("button", { key: value, onClick: () => value === "" ? grade === "" ? null : setGrade("") : setGrade(value), style: chipStyle(active) }, label);
  }
}
function statChip(color) {
  return {
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    padding: "4px 10px",
    background: "#f8fafc",
    color,
    fontWeight: 600,
    fontSize: 12
  };
}
function refreshStyle() {
  return {
    marginLeft: "auto",
    border: "1px solid #cbd5e1",
    borderRadius: 8,
    padding: "4px 10px",
    background: "#fff",
    cursor: "pointer",
    fontSize: 12
  };
}
function miniBtn(active, color) {
  return {
    border: active ? `2px solid ${color}` : "1px solid #cbd5e1",
    borderRadius: 6,
    padding: "2px 8px",
    marginRight: 6,
    cursor: "pointer",
    background: active ? color : "#fff",
    color: active ? "#fff" : "#475569",
    fontSize: 12
  };
}
function fmtSalary(j) {
  if (j.salary_min && j.salary_max) {
    return `${Math.round(j.salary_min / 1e3)}-${Math.round(j.salary_max / 1e3)}K`;
  }
  return "\u9762\u8BAE";
}

// src/client/index.ts
var NS = "dsh-job-radar";
var name = "dsh-job-radar";
var inject = ["slots", "locale"];
function apply(ctx) {
  ctx.effect(() => ctx.locale.register(NS, { zh: DICT_ZH, en: DICT_EN }), "dsh-job-radar: dictionaries");
  const t = ctx.locale.bind(NS);
  const reflectCtx = ctx;
  const remote = () => reflectCtx.reflect.get("remote.jobRadar");
  ctx.slots.inject("settings.section", () => ctx.slots.register({
    name: "settings.section",
    id: "job-radar",
    order: 30,
    label: () => t("nav"),
    locale: NS,
    inject: () => ({ hooks: { remote } })
  }, () => (0, import_react2.createElement)(RadarPanel, { hooks: { remote } })));
}
var DICT_ZH = { nav: "Job Radar \u5C97\u4F4D\u770B\u677F" };
var DICT_EN = { nav: "Job Radar Dashboard" };
return module.exports; } });
