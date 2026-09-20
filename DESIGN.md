---
name: 个人工作台
description: 暮光任务舱式的结论优先个人指挥台
colors:
  graphite-bg: "#09111d"
  panel-blue-black: "#0d1827"
  cool-line: "rgba(151, 177, 211, .14)"
  cool-line-strong: "rgba(95, 150, 255, .28)"
  text-primary: "#f2f6fb"
  text-secondary: "#aebed1"
  text-muted: "#71849b"
  cobalt-action: "#66a3ff"
  cyan-normal: "#46d9c2"
  amber-attention: "#f4b86a"
  coral-error: "#ff737c"
typography:
  headline:
    fontFamily: 'var(--dsw-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif)'
    fontSize: "25px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-.025em"
  conclusion:
    fontFamily: 'var(--dsw-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif)'
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: "-.02em"
  body:
    fontFamily: 'var(--dsw-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif)'
    fontSize: "12px"
  label:
    fontFamily: 'var(--dsw-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif)'
    fontSize: "10.5px"
rounded:
  control: "8px"
  inset: "9px"
  rail: "12px"
  container: "13px"
spacing:
  compact: "12px"
  standard: "16px"
  generous: "20px"
components:
  action-button:
    backgroundColor: "rgba(15, 31, 50, .75)"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  widget-card:
    backgroundColor: "linear-gradient(145deg, rgba(16, 30, 48, .94), rgba(11, 22, 36, .96))"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.container}"
    padding: "20px"
  status-rail:
    backgroundColor: "rgba(13, 24, 39, .82)"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.rail}"
---

# Design System: 个人工作台

## Overview

**Creative North Star: "暮光任务舱"**

界面像一间低照度、持续运行的任务舱：深石墨与冷蓝黑承载高密度状态，钴蓝标出可操作路径，青绿、琥珀与珊瑚红只承担明确的运行语义。科技感来自精密网格、克制边线、稳定位置和数字层级，而不是霓虹装饰。

首页先给出“是否正常”和最值得关注的结论，再以数字和列表作为证据。模块位置固定，异常只改变提醒与状态表达，不触发布局重排；没有大型欢迎区，也不把看板做成通用后台模板。

**Key Characteristics:**

- 深石墨与冷蓝黑的低照度工作环境
- 钴蓝交互、青绿正常、琥珀关注、珊瑚红异常
- 结论优先，数据作为判断证据
- 12 列固定项目网格与克制的响应式折叠
- 细冷色边线、低位柔和阴影、宿主字体

## Colors

色彩保持冷静、低饱和的舱室基底，让少量高辨识度状态色承担全部行动与健康语义。

### Primary

- **钴蓝交互：**用于图标、得分、等级、按钮边线与键盘焦点，建立单一而稳定的可操作线索。

### Secondary

- **青绿正常：**用于运行正常、工作区干净、S 级与机会值等正向证据。
- **琥珀关注：**用于阻塞、待处理和非致命异常，表示需要查看但不等同失败。
- **珊瑚红异常：**只用于读取失败、插件失败和明确错误。

### Neutral

- **深石墨背景：**作为整页底色，保持长时间使用时的低眩光。
- **冷蓝黑面板：**承载状态轨和业务模块，依靠细微明度差建立层级。
- **冷白正文：**用于标题、结论和关键值。
- **雾蓝次文与静音文：**分别承载解释、元数据与低优先级信息。
- **冷色细线：**分隔列表、围合卡片；强调线只出现在交互和图标容器。

### Named Rules

**The Semantic Color Rule.** 青绿、琥珀与珊瑚红必须对应正常、关注与异常，不把状态色当作无意义装饰。

**The No Neon Rule.** 保持低照度与克制对比，不使用霓虹光晕或高饱和赛博背景。

## Typography

**Display Font:** 宿主字体变量，回退至 PingFang SC、Microsoft YaHei、system-ui、sans-serif
**Body Font:** 与 Display 共用宿主字体栈
**Label/Mono Font:** 排名使用 ui-monospace、monospace；其余标签沿用宿主字体

**Character:** 字体完全服从宿主环境，以紧凑字号、负字距标题和等宽数字建立精密而不抢眼的仪表感。

### Hierarchy

- **Headline：**25px、1.25 行高、轻微负字距；仅用于页面标题。
- **Conclusion：**18px、650 字重、1.35 行高；用于每个项目最值得先读的判断。
- **Title：**17px 项目标题与 13px 小模块标题，建立模块归属。
- **Body：**11.5-13px；用于动作、岗位名称、解释和正文。
- **Label：**9-10.5px；用于元数据、状态说明与指标名，重要数字启用 tabular numerals。

### Named Rules

**The Conclusion First Rule.** 项目结论的字号和权重高于项目描述与元数据，数字不得反客为主。

## Layout

主内容覆盖宿主内容区，以 12 列网格和 12px 间距组织模块。两个主业务模块各占 6 列，同步中心占满 12 列；状态轨固定在其上方，项目位置不随状态变化。主模块内部使用 20px 留白，紧凑区域使用 12-16px 节奏。

在 900px 以下，状态轨变为两列，主业务模块各占整行，同步指标换至下一行；在 560px 以下，页面水平留白收紧至 16px，状态轨单列，主模块内边距降至 16px，同步指标变为两列网格。响应式只改变列数与换行，不改变信息优先级或项目顺序。

**The Fixed Position Rule.** 状态变化只改变语义提示，不自动重排项目模块。

## Elevation & Depth

系统以色调分层和细冷色边线为主，以低位柔和阴影为辅。模块卡片使用向下扩散的环境阴影，状态点使用更小的局部阴影；交互反馈依靠背景与边线变亮，不使用悬浮抬升或发光。

### Shadow Vocabulary

- **模块环境阴影** (`0 12px 30px rgba(0,0,0,.18)`): 仅用于主卡片与同步卡片，使其从背景轻微分离。
- **状态点阴影** (`0 2px 8px rgba(0,0,0,.35)`): 帮助 7px 状态点在深色表面上保持轮廓。

### Named Rules

**The Low Lift Rule.** 阴影只提供低位层级，不把卡片塑造成漂浮面板。

## Shapes

外层模块使用 13px 圆角，状态轨使用 12px；按钮、等级徽记使用 8px，图标容器和结论内嵌面使用 9px。所有容器由 1px 冷色细线收边，状态点保持圆形。圆角差异反映容器尺度，不用于制造活泼或软糖感。

## Components

### Buttons

- **Shape:** 紧凑矩形控制（8px 圆角），7px × 10px 内边距，图标与文字间距 7px。
- **Primary:** 当前实现采用深蓝黑半透明底、冷色强调边线和雾蓝文字；页面没有实心 CTA。
- **Hover / Focus:** 悬停时文字转冷白、背景与边线提亮；键盘焦点使用 2px 钴蓝外轮廓与 3px 偏移。

### Chips

- **Style:** 岗位等级是 32px 方形徽记，8px 圆角、强调边线与钴蓝文字；S 级转为青绿。
- **State:** 等级颜色传达分类，但文本字母始终保留，状态不只依赖颜色。

### Cards / Containers

- **Corner Style:** 主模块采用 13px 圆角，状态轨采用 12px 圆角。
- **Background:** 主模块为冷蓝黑斜向渐变，状态轨为半透明冷蓝黑。
- **Shadow Strategy:** 仅主模块使用模块环境阴影；状态轨依靠边线和底色分层。
- **Border:** 统一 1px 冷色细线，交互性图标容器使用更强的冷蓝边线。
- **Internal Padding:** 主模块 20px，窄屏 16px；状态单元 13px × 16px。

### Navigation

- 首页本身不实现一级导航，沿用宿主侧栏；模块内入口使用紧凑文字按钮并带右向箭头，固定在模块标题区或同步条右端。

### Health Rail

四个等宽状态槽先给出全局运行、业务项目、代码同步和宿主状态。7px 色点与明确文本共同表达状态；最后一槽在无异常时显示低干扰说明，在异常时替换为红色宿主错误。

### Evidence Rows

岗位与机会维度都使用稳定的水平行、底部分隔线和右对齐关键值。内容过长时截断或自然换行，关键数值使用 tabular numerals；列表末行移除分隔线。

## Do's and Don'ts

### Do:

- **Do** 先呈现运行结论，再呈现列表、指标与解释证据。
- **Do** 保持项目固定位置，并在 900px 与 560px 断点按既定顺序折叠。
- **Do** 沿用宿主字体与键盘焦点，确保颜色之外仍有文本和结构提示。
- **Do** 使用细冷色边线与低位阴影维持层级。

### Don't:

- **Don't** 使用霓虹光、强烈赛博装饰或高饱和大面积背景。
- **Don't** 加入占据首屏的大型欢迎语、装饰性 Hero 或无信息价值占位。
- **Don't** 因状态或排序变化自动移动项目模块。
- **Don't** 把首页变成复杂写操作或完整配置入口。
