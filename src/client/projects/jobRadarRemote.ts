/**
 * `remote.jobRadar` 的适配层 —— 把「Cordis 服务对象」翻译成项目契约里的
 * `JobRadarFace`。
 *
 * 两个必须在这里抹平的差异，都不是风格问题：
 *
 *   1. **信封**。网关对每次调用返回 `{ ok, value } | { ok, error }`，而
 *      `JobRadarFace` 承诺的是直接的 `{ jobs, total }`。不拆信封的话
 *      `res.jobs` 恒为 `undefined`，列表会「成功地」渲染成空。
 *
 *   2. **参数个数**。宿主半部的 `@Remote` 标记没有经过 Typert 构建流程，
 *      网关因此走 source-mode 兜底，并按描述符声明的
 *      `parameters.length` 校验实参个数 —— 多一个少一个都会被拒绝
 *      （`client api: jobRadar/list expected 1 argument(s), got 0`）。
 *      `list` 声明了 1 个参数，所以调用方**必须**至少传一个，哪怕只是 `{}`。
 *      项目侧把 filter 写成可选是合理的，补齐就在这里做。
 *
 * 命名空间按调用实时解析、绝不缓存：它由另一个插件的客户端半部在
 * `ctx.remote.$mount(...)` 之后才出现，早于那一刻拿到的 `undefined`
 * 不代表之后也没有。
 */
import type { JobRadarFace, JobRecord } from './types.ts'

/** 网关的每次调用信封。 */
interface RemoteResult<T> {
  ok?: boolean
  value?: T
  error?: { code?: string; message?: string }
}

/** 从 `ctx.reflect.get('remote.jobRadar')` 拿到的原始服务对象。 */
type RawNamespace = Record<string, (...args: unknown[]) => Promise<RemoteResult<unknown>>>

/** 拆信封：成功给值，失败抛错 —— 项目侧写的是 `await list()`，不是 `await list().ok`。 */
async function unwrap<T>(call: Promise<RemoteResult<T>>, method: string): Promise<T> {
  const result = await call
  if (result === null || typeof result !== 'object' || result.ok !== true) {
    throw new Error(result?.error?.message ?? `jobRadar.${method} 调用失败`)
  }
  return result.value as T
}

/**
 * 把原始命名空间包成项目可直接使用的面。
 * @param raw - `ctx.reflect.get('remote.jobRadar')` 的结果，可能是 `undefined`。
 * @returns 适配后的面，或 `undefined`（表示 job-radar 插件没装载）。
 */
export function toJobRadarFace(raw: unknown): JobRadarFace | undefined {
  if (raw === null || typeof raw !== 'object') return undefined
  const ns = raw as RawNamespace
  if (typeof ns.list !== 'function' || typeof ns.stats !== 'function' || typeof ns.setStatus !== 'function') {
    // 装载到一半的命名空间：按「没装载」处理，让项目渲染未装载态而不是抛错。
    return undefined
  }
  return {
    // `?? {}` 不是防御性冗余 —— 少了它这次调用会被网关按参数个数拒掉。
    list: (filter) => unwrap<{ jobs: readonly JobRecord[]; total: number }>(ns.list(filter ?? {}), 'list'),
    stats: () => unwrap<Record<string, number>>(ns.stats(), 'stats'),
    setStatus: (id, status) =>
      unwrap<{ ok: boolean; error?: string }>(ns.setStatus(id, status), 'setStatus'),
  }
}
