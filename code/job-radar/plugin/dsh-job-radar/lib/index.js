var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __knownSymbol = (name2, symbol) => (symbol = Symbol[name2]) ? symbol : /* @__PURE__ */ Symbol.for("Symbol." + name2);
var __typeError = (msg) => {
  throw TypeError(msg);
};
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });
var __decoratorStart = (base) => [, , , __create(base?.[__knownSymbol("metadata")] ?? null)];
var __decoratorStrings = ["class", "method", "getter", "setter", "accessor", "field", "value", "get", "set"];
var __expectFn = (fn) => fn !== void 0 && typeof fn !== "function" ? __typeError("Function expected") : fn;
var __decoratorContext = (kind, name2, done, metadata, fns) => ({ kind: __decoratorStrings[kind], name: name2, metadata, addInitializer: (fn) => done._ ? __typeError("Already initialized") : fns.push(__expectFn(fn || null)) });
var __decoratorMetadata = (array, target) => __defNormalProp(target, __knownSymbol("metadata"), array[3]);
var __runInitializers = (array, flags, self, value) => {
  for (var i = 0, fns = array[flags >> 1], n = fns && fns.length; i < n; i++) flags & 1 ? fns[i].call(self) : value = fns[i].call(self, value);
  return value;
};
var __decorateElement = (array, flags, name2, decorators, target, extra) => {
  var fn, it, done, ctx, access, k = flags & 7, s = !!(flags & 8), p = !!(flags & 16);
  var j = k > 3 ? array.length + 1 : k ? s ? 1 : 2 : 0, key = __decoratorStrings[k + 5];
  var initializers = k > 3 && (array[j - 1] = []), extraInitializers = array[j] || (array[j] = []);
  var desc = k && (!p && !s && (target = target.prototype), k < 5 && (k > 3 || !p) && __getOwnPropDesc(k < 4 ? target : { get [name2]() {
    return __privateGet(this, extra);
  }, set [name2](x) {
    return __privateSet(this, extra, x);
  } }, name2));
  k ? p && k < 4 && __name(extra, (k > 2 ? "set " : k > 1 ? "get " : "") + name2) : __name(target, name2);
  for (var i = decorators.length - 1; i >= 0; i--) {
    ctx = __decoratorContext(k, name2, done = {}, array[3], extraInitializers);
    if (k) {
      ctx.static = s, ctx.private = p, access = ctx.access = { has: p ? (x) => __privateIn(target, x) : (x) => name2 in x };
      if (k ^ 3) access.get = p ? (x) => (k ^ 1 ? __privateGet : __privateMethod)(x, target, k ^ 4 ? extra : desc.get) : (x) => x[name2];
      if (k > 2) access.set = p ? (x, y) => __privateSet(x, target, y, k ^ 4 ? extra : desc.set) : (x, y) => x[name2] = y;
    }
    it = (0, decorators[i])(k ? k < 4 ? p ? extra : desc[key] : k > 4 ? void 0 : { get: desc.get, set: desc.set } : target, ctx), done._ = 1;
    if (k ^ 4 || it === void 0) __expectFn(it) && (k > 4 ? initializers.unshift(it) : k ? p ? extra = it : desc[key] = it : target = it);
    else if (typeof it !== "object" || it === null) __typeError("Object expected");
    else __expectFn(fn = it.get) && (desc.get = fn), __expectFn(fn = it.set) && (desc.set = fn), __expectFn(fn = it.init) && initializers.unshift(fn);
  }
  return k || __decoratorMetadata(array, target), desc && __defProp(target, name2, desc), p ? k ^ 4 ? extra : desc : target;
};
var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
var __privateIn = (member, obj) => Object(obj) !== obj ? __typeError('Cannot use the "in" operator on this value') : member.has(obj);
var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);

// src/index.ts
import { Remote, TypertRemoteService } from "@deepseek-ai/dsh-typert-protocol";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
var name = "dsh-job-radar";
var inject = [];
var ALL_STATUS = ["new", "applied", "interested", "rejected"];
var _setStatus_dec, _stats_dec, _list_dec, _ping_dec, _a, _init;
var JobRadarRuntime = class extends (_a = TypertRemoteService, _ping_dec = [Remote], _list_dec = [Remote], _stats_dec = [Remote], _setStatus_dec = [Remote], _a) {
  constructor(ctx, dataDir) {
    super(ctx, "jobRadar");
    __runInitializers(_init, 5, this);
    this.snapshotPath = void 0;
    this.log = void 0;
    this.snapshotPath = join(dataDir, "jobs.json");
    this.log = ctx.logger;
  }
  readSnapshot() {
    try {
      if (!existsSync(this.snapshotPath)) return { jobs: [] };
      const data = JSON.parse(readFileSync(this.snapshotPath, "utf-8"));
      return { jobs: Array.isArray(data.jobs) ? data.jobs : [] };
    } catch (err) {
      this.log.warn(`[dsh-job-radar] read jobs.json failed: ${err.message}`);
      return { jobs: [] };
    }
  }
  writeSnapshot(jobs) {
    try {
      writeFileSync(
        this.snapshotPath,
        JSON.stringify({ version: 1, exported_at: (/* @__PURE__ */ new Date()).toISOString(), jobs }, null, 2),
        "utf-8"
      );
    } catch (err) {
      this.log.warn(`[dsh-job-radar] write jobs.json failed: ${err.message}`);
    }
  }
  ping() {
    return { ok: true };
  }
  list(filter) {
    const { jobs } = this.readSnapshot();
    const f = filter ?? {};
    let out = jobs;
    if (f.grade) out = out.filter((j) => j.grade === f.grade);
    if (f.status) out = out.filter((j) => j.status === f.status);
    if (f.days) {
      const cutoff = Date.now() - f.days * 864e5;
      out = out.filter((j) => {
        const t = j.created_at ? Date.parse(j.created_at) : 0;
        return !Number.isNaN(t) && t >= cutoff;
      });
    }
    out = [...out].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    return { jobs: out, total: out.length };
  }
  stats() {
    const { jobs } = this.readSnapshot();
    const s = { total: jobs.length };
    for (const j of jobs) {
      s[`grade_${j.grade}`] = (s[`grade_${j.grade}`] ?? 0) + 1;
      s[`status_${j.status}`] = (s[`status_${j.status}`] ?? 0) + 1;
    }
    return s;
  }
  setStatus(jid, status) {
    if (!ALL_STATUS.includes(status)) return { ok: false, error: `invalid status: ${status}` };
    const { jobs } = this.readSnapshot();
    const idx = jobs.findIndex((j) => j.id === jid);
    if (idx < 0) return { ok: false, error: `job not found: ${jid}` };
    jobs[idx] = { ...jobs[idx], status, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    this.writeSnapshot(jobs);
    return { ok: true };
  }
};
_init = __decoratorStart(_a);
__decorateElement(_init, 1, "ping", _ping_dec, JobRadarRuntime);
__decorateElement(_init, 1, "list", _list_dec, JobRadarRuntime);
__decorateElement(_init, 1, "stats", _stats_dec, JobRadarRuntime);
__decorateElement(_init, 1, "setStatus", _setStatus_dec, JobRadarRuntime);
__decoratorMetadata(_init, JobRadarRuntime);
function apply(ctx, config) {
  const dataDir = config?.dataDir ?? "";
  if (!dataDir) {
    ctx.logger.warn("[dsh-job-radar] dataDir not configured \u2014 dashboard disabled. Set it in the profile patch: config.dataDir");
    return;
  }
  new JobRadarRuntime(ctx, dataDir);
  ctx.logger.info(`[dsh-job-radar] mounted, dataDir=${dataDir}`);
}
export {
  JobRadarRuntime,
  apply,
  inject,
  name
};
