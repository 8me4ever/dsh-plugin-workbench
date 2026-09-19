/**
 * `remote.tablewareRadar` 的适配层 —— 把「Cordis 服务对象」翻译成项目契约里的
 * `TablewareRadarFace`。
 *
 * 与 `jobRadarRemote.ts` 同源，两个必须抹平的差异：
 *
 *   1. **拆信封**。网关每次调用返回 `{ ok, value } | { ok, error }`，而
 *      `TablewareRadarFace` 承诺直接给 `TablewareAnalysis | null` / `TablewareStatus`。
 *      不拆信封的话 `value` 恒为 `undefined`，界面会「成功地」渲染成空。
 *
 *   2. **参数个数**。网关按描述符声明的 `parameters.length` 严格校验实参个数。
 *      本项目两个方法（`getAnalysis` / `getStatus`）都声明 **0 个参数**，
 *      所以这里**必须**无参调用 —— 多传一个 `{}` 都会被拒。
 *
 * 命名空间按调用实时解析、绝不缓存：它由另一个插件（dsh-tableware-radar）的
 * 客户端半部在 `ctx.remote.$mount(...)` 之后才出现，早于那一刻拿到的
 * `undefined` 不代表之后也没有。
 */
import type { TablewareAnalysis, TablewareRadarFace, TablewareStatus } from './types.ts'

/** 网关的每次调用信封。 */
interface RemoteResult<T> {
  ok?: boolean
  value?: T
  error?: { code?: string; message?: string }
}

/** 从 `ctx.reflect.get('remote.tablewareRadar')` 拿到的原始服务对象。 */
type RawNamespace = Record<string, (...args: unknown[]) => Promise<RemoteResult<unknown>>>

/** 拆信封：成功给值，失败抛错。 */
async function unwrap<T>(call: Promise<RemoteResult<T>>, method: string): Promise<T> {
  const result = await call
  if (result === null || typeof result !== 'object' || result.ok !== true) {
    throw new Error(result?.error?.message ?? `tablewareRadar.${method} 调用失败`)
  }
  return result.value as T
}

/**
 * 把原始命名空间包成项目可直接使用的面。
 * @param raw - `ctx.reflect.get('remote.tablewareRadar')` 的结果，可能是 `undefined`。
 * @returns 适配后的面，或 `undefined`（表示 dsh-tableware-radar 插件没装载）。
 */
export function toTablewareRadarFace(raw: unknown): TablewareRadarFace | undefined {
  if (raw === null || typeof raw !== 'object') return undefined
  const ns = raw as RawNamespace
  if (typeof ns.getAnalysis !== 'function' || typeof ns.getStatus !== 'function') {
    // 装载到一半的命名空间：按「没装载」处理，让项目渲染未装载态而不是抛错。
    return undefined
  }
  return {
    // 两个方法都是 0 参数 —— 不能补任何实参，否则会被网关按参数个数拒掉。
    getAnalysis: () => unwrap<TablewareAnalysis | null>(ns.getAnalysis(), 'getAnalysis'),
    getStatus: () => unwrap<TablewareStatus>(ns.getStatus(), 'getStatus'),
  }
}
