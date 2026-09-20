"""tableware-radar 离线数据管道。

模块划分（详见 ``../docs/ARCHITECTURE.md`` §2.1）：

    config        —— 全部可调参数与路径常量（唯一配置入口）
    models        —— 纯数据类（RawReview / ReviewRecord / Label / Dimension / Analysis …）
    fetch.*       —— 薄抓取接口（Fetcher Protocol + fixture / amazon_uk 实现）
    clean         —— 清洗去重
    llm.*         —— dsh headless 子进程 LLM 客户端 + Prompt
    dimensions    —— dimensions.yaml 加载与校验
    stage_a_topics—— 阶段 A 开放编码
    stage_c_label —— 阶段 C 封闭打标 + 闸门 + 降级
    aggregate     —— 聚合打分 → analysis.json
    cli           —— 端到端编排入口
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
