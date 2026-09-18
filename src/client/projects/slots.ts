/**
 * ★★★ 四个项目位就在这里 —— 这是你唯一需要改的文件。★★★
 *
 * 数组的每一项对应工作台左侧导航里的一个位置，顺序即显示顺序。
 * 项目 01 已经被 Job Radar 占了，剩下三个还是 `null`，页面上显示三张
 * 「预留位」占位卡片。
 *
 * 接入一个项目的完整流程：
 *
 *   1. 在同级目录新建一个文件，例如 `myProject.ts`：
 *
 *      ```ts
 *      import { createElement as h } from 'react'
 *      import type { WorkbenchProject } from './types.ts'
 *
 *      export const myProject: WorkbenchProject = {
 *        id: 'my-project',
 *        title: () => '我的项目',
 *        summary: () => '在这里写一句说明',
 *        render: (ctx) => h('div', null, `宿主共装载 ${ctx.inventory.get().entries.length} 个插件`),
 *      }
 *      ```
 *
 *   2. 在下面把对应的 `null` 换成它：
 *
 *      ```ts
 *      import { myProject } from './myProject.ts'
 *
 *      export const PROJECT_SLOTS: readonly ProjectSlot[] = [jobRadarProject, myProject, null, null]
 *      ```
 *
 *   3. 回项目根目录跑一次 `node scripts/dev.mjs`（构建 + 重装 + 提示重启），
 *      刷新浏览器即可看到。注意：不重装的话页面还是旧的，原因见 README。
 *
 * 想加第五个项目？直接往数组里再 push 一项即可 —— 工作台按数组长度渲染，
 * 没有写死"四个"这个数字。四个只是当前的预留数量。
 *
 * 项目需要宿主数据（文件、网络、进程）时，两条路都行，`jobRadar.ts` 是
 * 第一条的现成样板：消费一个**已经存在**的 Remote，并把它当可选依赖处理。
 * 若没有现成 Remote 可用，就去 `src/index.ts` 给宿主半部加 `@Remote`
 * 方法，再从项目里解析 `remote.<namespace>`。
 */
import type { ProjectSlot } from './types.ts'
import { jobRadarProject } from './jobRadar.ts'

export const PROJECT_SLOTS: readonly ProjectSlot[] = [
  jobRadarProject, // 项目 01 —— Job Radar 岗位看板
  null, // 项目 02 —— 预留
  null, // 项目 03 —— 预留
  null, // 项目 04 —— 预留
]
