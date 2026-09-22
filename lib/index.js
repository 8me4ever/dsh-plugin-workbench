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
import { existsSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { isAbsolute, join, resolve, sep } from "node:path";
import { execFileSync } from "node:child_process";
var name = "dsh-plugin-workbench";
var inject = [];
var STATUS = /* @__PURE__ */ new Set(["new", "applied", "interested", "rejected"]);
var LOCATION_FILE = join(homedir(), ".dsh", "dsh-plugin-workbench.json");
function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return void 0;
  }
}
function resolveWorkspace(config) {
  if (config?.workspaceDir) return resolve(config.workspaceDir);
  if (process.env.DSH_WORKBENCH_ROOT) return resolve(process.env.DSH_WORKBENCH_ROOT);
  const registered = readJson(LOCATION_FILE)?.workspaceDir;
  if (typeof registered === "string" && registered) return resolve(registered);
  return process.cwd();
}
function resolveDataDir(workspace, override, fallback) {
  if (!override) return join(workspace, fallback);
  return isAbsolute(override) ? override : resolve(workspace, override);
}
function atomicJsonWrite(path, value) {
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}
`, "utf8");
  renameSync(temporary, path);
}
var _setStatus_dec, _stats_dec, _list_dec, _ping_dec, _a, _init;
var JobRadarRuntime = class extends (_a = TypertRemoteService, _ping_dec = [Remote], _list_dec = [Remote], _stats_dec = [Remote], _setStatus_dec = [Remote], _a) {
  constructor(ctx, dataDir) {
    super(ctx, "jobRadar");
    __runInitializers(_init, 5, this);
    this.snapshotPath = void 0;
    this.snapshotPath = join(dataDir, "jobs.json");
  }
  snapshot() {
    const data = readJson(this.snapshotPath);
    return { version: data?.version, exported_at: data?.exported_at, jobs: Array.isArray(data?.jobs) ? data.jobs : [] };
  }
  ping() {
    return { ok: true };
  }
  list(filter) {
    const f = filter ?? {};
    let jobs = this.snapshot().jobs;
    if (f.grade) jobs = jobs.filter((job) => job.grade === f.grade);
    if (f.status) jobs = jobs.filter((job) => job.status === f.status);
    if (f.days) {
      const cutoff = Date.now() - f.days * 864e5;
      jobs = jobs.filter((job) => {
        const created = Date.parse(job.created_at ?? "");
        return !Number.isNaN(created) && created >= cutoff;
      });
    }
    jobs = [...jobs].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    return { jobs, total: jobs.length };
  }
  stats() {
    const jobs = this.snapshot().jobs;
    const stats = { total: jobs.length };
    for (const job of jobs) {
      stats[`grade_${job.grade}`] = (stats[`grade_${job.grade}`] ?? 0) + 1;
      stats[`status_${job.status}`] = (stats[`status_${job.status}`] ?? 0) + 1;
    }
    return stats;
  }
  setStatus(jobId, status) {
    if (!STATUS.has(status)) return { ok: false, error: `invalid status: ${status}` };
    const snapshot = this.snapshot();
    const index = snapshot.jobs.findIndex((job) => job.id === jobId);
    if (index < 0) return { ok: false, error: `job not found: ${jobId}` };
    snapshot.jobs[index] = { ...snapshot.jobs[index], status, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    atomicJsonWrite(this.snapshotPath, {
      version: snapshot.version ?? 1,
      exported_at: (/* @__PURE__ */ new Date()).toISOString(),
      jobs: snapshot.jobs
    });
    return { ok: true };
  }
};
_init = __decoratorStart(_a);
__decorateElement(_init, 1, "ping", _ping_dec, JobRadarRuntime);
__decorateElement(_init, 1, "list", _list_dec, JobRadarRuntime);
__decorateElement(_init, 1, "stats", _stats_dec, JobRadarRuntime);
__decorateElement(_init, 1, "setStatus", _setStatus_dec, JobRadarRuntime);
__decoratorMetadata(_init, JobRadarRuntime);
var _getStatus_dec, _getAnalysis_dec, _a2, _init2;
var TablewareRadarRuntime = class extends (_a2 = TypertRemoteService, _getAnalysis_dec = [Remote], _getStatus_dec = [Remote], _a2) {
  constructor(ctx, dataDir) {
    super(ctx, "tablewareRadar");
    __runInitializers(_init2, 5, this);
    this.analysisPath = void 0;
    this.analysisPath = join(dataDir, "analysis.json");
  }
  getAnalysis() {
    return readJson(this.analysisPath) ?? null;
  }
  getStatus() {
    try {
      const stat = statSync(this.analysisPath);
      const analysis = readJson(this.analysisPath);
      return {
        present: true,
        path: this.analysisPath,
        mtimeMs: stat.mtimeMs,
        bytes: stat.size,
        generatedAt: typeof analysis?.generated_at === "string" ? analysis.generated_at : null
      };
    } catch {
      return { present: false, path: this.analysisPath, mtimeMs: 0, bytes: 0, generatedAt: null };
    }
  }
};
_init2 = __decoratorStart(_a2);
__decorateElement(_init2, 1, "getAnalysis", _getAnalysis_dec, TablewareRadarRuntime);
__decorateElement(_init2, 1, "getStatus", _getStatus_dec, TablewareRadarRuntime);
__decoratorMetadata(_init2, TablewareRadarRuntime);
var MAX_COMMIT_FILE_BYTES = 5 * 1024 * 1024;
var MAX_DIFF_CHARS = 16e4;
var SENSITIVE_PATH = /(?:^|\/)(?:\.env(?:\.|$)|\.npmrc$|credentials?(?:\.|$)|secrets?(?:\.|$)|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|$)|[^/]+\.(?:pem|key|p12|pfx))|(?:^|\/)[^/]*(?:token|secret)[^/]*$/i;
var _commit_dec, _commitPreview_dec, _preview_dec, _refresh_dec, _a3, _init3;
var WorkbenchSyncRuntime = class extends (_a3 = TypertRemoteService, _refresh_dec = [Remote], _preview_dec = [Remote], _commitPreview_dec = [Remote], _commit_dec = [Remote], _a3) {
  constructor(ctx, workspace) {
    super(ctx, "workbenchSync");
    this.workspace = workspace;
    __runInitializers(_init3, 5, this);
  }
  git(args) {
    return execFileSync("git", args, {
      cwd: this.workspace,
      encoding: "utf8",
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    }).trimEnd();
  }
  safePath(path) {
    if (!path || path.includes("\0")) throw new Error("\u6587\u4EF6\u8DEF\u5F84\u65E0\u6548");
    const absolute = resolve(this.workspace, path);
    const root = resolve(this.workspace);
    if (absolute !== root && !absolute.startsWith(`${root}${sep}`)) throw new Error(`\u6587\u4EF6\u4E0D\u5728\u5DE5\u4F5C\u53F0\u4ED3\u5E93\u4E2D\uFF1A${path}`);
    return absolute;
  }
  fileInfo(path, tracked) {
    const normalized = path.replace(/\\/g, "/");
    if (normalized.includes(" -> ")) return { bytes: 0, blocker: "\u91CD\u547D\u540D\u6587\u4EF6\u6682\u4E0D\u652F\u6301\u5728\u5DE5\u4F5C\u53F0\u5185\u63D0\u4EA4\uFF0C\u8BF7\u4F7F\u7528 Git \u547D\u4EE4\u5904\u7406" };
    if (SENSITIVE_PATH.test(normalized)) return { bytes: 0, blocker: "\u7591\u4F3C\u5305\u542B\u5BC6\u94A5\u3001\u51ED\u636E\u6216 Token\uFF0C\u4E0D\u5141\u8BB8\u4ECE\u5DE5\u4F5C\u53F0\u63D0\u4EA4" };
    try {
      const stat = statSync(this.safePath(path));
      if (!stat.isFile()) return { bytes: stat.size, blocker: "\u4E0D\u662F\u666E\u901A\u6587\u4EF6\uFF0C\u4E0D\u80FD\u4ECE\u5DE5\u4F5C\u53F0\u63D0\u4EA4" };
      if (stat.size > MAX_COMMIT_FILE_BYTES) return { bytes: stat.size, blocker: `\u6587\u4EF6\u8D85\u8FC7 ${MAX_COMMIT_FILE_BYTES / 1024 / 1024} MB \u9650\u5236` };
      return { bytes: stat.size };
    } catch {
      return tracked ? { bytes: 0 } : { bytes: 0, blocker: "\u6587\u4EF6\u4E0D\u5B58\u5728\u6216\u65E0\u6CD5\u8BFB\u53D6" };
    }
  }
  status(fetchedAt) {
    const branch = this.git(["branch", "--show-current"]);
    const counts = this.git(["rev-list", "--left-right", "--count", "HEAD...origin/main"]).split(/\s+/);
    const raw = this.git(["status", "--porcelain=v1", "-z", "--untracked-files=all"]);
    const entries = raw ? raw.split("\0").filter(Boolean) : [];
    const files = [];
    for (let index = 0; index < entries.length; index += 1) {
      const line = entries[index];
      const tracked = !line.startsWith("??");
      const path = line.slice(3);
      const status = line.slice(0, 2);
      const info = this.fileInfo(path, tracked);
      if (/[RC]/.test(status)) {
        index += 1;
        info.blocker = "\u91CD\u547D\u540D\u6216\u590D\u5236\u6587\u4EF6\u6682\u4E0D\u652F\u6301\u5728\u5DE5\u4F5C\u53F0\u5185\u63D0\u4EA4\uFF0C\u8BF7\u4F7F\u7528 Git \u547D\u4EE4\u5904\u7406";
      }
      files.push({ status, path, tracked, ...info });
    }
    const localCommits = this.git(["log", "--format=%h %s", "origin/main..HEAD"]).split("\n").filter(Boolean);
    const remoteCommits = this.git(["log", "--format=%h %s", "HEAD..origin/main"]).split("\n").filter(Boolean);
    const blockers = [];
    if (branch !== "main") blockers.push(`\u5F53\u524D\u5206\u652F\u662F ${branch || "(detached)"}\uFF0C\u540C\u6B65\u53EA\u652F\u6301 main`);
    if (files.some((file) => /(?:U|AA|DD)/.test(file.status))) blockers.push("\u5DE5\u4F5C\u533A\u5B58\u5728\u5C1A\u672A\u89E3\u51B3\u7684 Git \u51B2\u7A81");
    return {
      branch,
      isMain: branch === "main",
      ahead: Number(counts[0] ?? 0),
      behind: Number(counts[1] ?? 0),
      files,
      localCommits,
      remoteCommits,
      blockers,
      fetchedAt
    };
  }
  refresh() {
    this.git(["fetch", "--prune", "origin", "main"]);
    return this.status((/* @__PURE__ */ new Date()).toISOString());
  }
  preview() {
    return this.status((/* @__PURE__ */ new Date()).toISOString());
  }
  validateMessage(message) {
    const clean = message.trim();
    if (!clean) throw new Error("\u63D0\u4EA4\u8BF4\u660E\u4E0D\u80FD\u4E3A\u7A7A");
    if (clean.length > 200) throw new Error("\u63D0\u4EA4\u8BF4\u660E\u4E0D\u80FD\u8D85\u8FC7 200 \u4E2A\u5B57\u7B26");
    return clean;
  }
  selectedFiles(paths) {
    const unique = [...new Set(paths)];
    if (unique.length === 0) throw new Error("\u8BF7\u81F3\u5C11\u9009\u62E9\u4E00\u4E2A\u6587\u4EF6");
    const current = this.status((/* @__PURE__ */ new Date()).toISOString());
    if (current.blockers.length) throw new Error(current.blockers.join("\n"));
    const byPath = new Map(current.files.map((file) => [file.path, file]));
    return unique.map((path) => {
      this.safePath(path);
      const file = byPath.get(path);
      if (!file) throw new Error(`\u6587\u4EF6\u5DF2\u53D8\u5316\u6216\u4E0D\u518D\u5B58\u5728\u4E8E\u5F85\u63D0\u4EA4\u5217\u8868\uFF1A${path}`);
      if (file.blocker) throw new Error(`${path}\uFF1A${file.blocker}`);
      return file;
    });
  }
  fileDiff(file) {
    if (file.tracked) return this.git(["diff", "--no-ext-diff", "--no-color", "HEAD", "--", file.path]);
    const content = readFileSync(this.safePath(file.path));
    if (content.includes(0)) return `diff --git a/${file.path} b/${file.path}
new file mode 100644
Binary file ${file.path} added`;
    const body = content.toString("utf8").split(/\r?\n/).map((line) => `+${line}`).join("\n");
    return `diff --git a/${file.path} b/${file.path}
new file mode 100644
--- /dev/null
+++ b/${file.path}
@@ -0,0 +1 @@
${body}`;
  }
  makePreview(paths, message) {
    const cleanMessage = this.validateMessage(message);
    const files = this.selectedFiles(paths);
    const fullDiff = files.map((file) => this.fileDiff(file)).filter(Boolean).join("\n\n");
    const truncated = fullDiff.length > MAX_DIFF_CHARS;
    const diff = truncated ? `${fullDiff.slice(0, MAX_DIFF_CHARS)}

\u2026 diff \u5DF2\u622A\u65AD \u2026` : fullDiff;
    const warnings = files.filter((file) => file.status[0] !== " " && file.status[0] !== "?").map((file) => `${file.path} \u5DF2\u6709\u6682\u5B58\u5185\u5BB9\uFF1B\u672C\u6B21\u5C06\u63D0\u4EA4\u8BE5\u6587\u4EF6\u5F53\u524D\u7684\u5B8C\u6574\u6539\u52A8`);
    const fingerprint = JSON.stringify({ paths: files.map((file) => file.path), message: cleanMessage, diff: fullDiff });
    return {
      paths: files.map((file) => file.path),
      message: cleanMessage,
      diff,
      truncated,
      warnings,
      token: createHash("sha256").update(fingerprint).digest("hex")
    };
  }
  commitPreview(paths, message) {
    return this.makePreview(paths, message);
  }
  commit(paths, message, previewToken) {
    const preview = this.makePreview(paths, message);
    if (preview.token !== previewToken) throw new Error("\u6587\u4EF6\u5728\u9884\u89C8\u540E\u53D1\u751F\u4E86\u53D8\u5316\uFF0C\u8BF7\u91CD\u65B0\u751F\u6210\u63D0\u4EA4\u9884\u89C8");
    const indexPathRaw = this.git(["rev-parse", "--git-path", "index"]);
    const indexPath = isAbsolute(indexPathRaw) ? indexPathRaw : resolve(this.workspace, indexPathRaw);
    const oldIndex = existsSync(indexPath) ? readFileSync(indexPath) : null;
    try {
      this.git(["add", "-A", "--", ...preview.paths]);
      this.git(["commit", "--only", "-m", preview.message, "--", ...preview.paths]);
    } catch (reason) {
      if (oldIndex === null) rmSync(indexPath, { force: true });
      else writeFileSync(indexPath, oldIndex);
      throw reason;
    }
    return { commit: this.git(["rev-parse", "--short", "HEAD"]), status: this.status((/* @__PURE__ */ new Date()).toISOString()) };
  }
};
_init3 = __decoratorStart(_a3);
__decorateElement(_init3, 1, "refresh", _refresh_dec, WorkbenchSyncRuntime);
__decorateElement(_init3, 1, "preview", _preview_dec, WorkbenchSyncRuntime);
__decorateElement(_init3, 1, "commitPreview", _commitPreview_dec, WorkbenchSyncRuntime);
__decorateElement(_init3, 1, "commit", _commit_dec, WorkbenchSyncRuntime);
__decoratorMetadata(_init3, WorkbenchSyncRuntime);
function apply(ctx, config) {
  const workspace = resolveWorkspace(config);
  const jobDataDir = resolveDataDir(workspace, config?.jobDataDir, "projects/job-hunting/code/job-radar/data");
  const tablewareDataDir = resolveDataDir(workspace, config?.tablewareDataDir, "projects/tableware-radar/data");
  new JobRadarRuntime(ctx, jobDataDir);
  new TablewareRadarRuntime(ctx, tablewareDataDir);
  new WorkbenchSyncRuntime(ctx, workspace);
  ctx.logger.info(`[dsh-plugin-workbench] unified host mounted; workspace=${workspace}`);
  if (!existsSync(workspace)) ctx.logger.warn(`[dsh-plugin-workbench] workspace does not exist: ${workspace}`);
}
export {
  JobRadarRuntime,
  TablewareRadarRuntime,
  WorkbenchSyncRuntime,
  apply,
  inject,
  name
};
