"""LLM 访问层：dsh headless 子进程客户端 + Prompt 库。

★ 头号技术决策落地（docs/ARCHITECTURE.md §1.3）：走
``node <dsh bin.js> --profile headless "<task>"`` 子进程，**批量调用**，
**只解析 stdout**（推理增量走 stderr，不污染结果）。
"""

from __future__ import annotations

from .client import (
    BatchResult,
    DshHeadlessClient,
    LlmEnvironmentError,
    LlmError,
    LlmParseError,
    LlmProcessError,
    LlmTimeoutError,
    extract_json,
    find_dsh_entry,
    find_node,
)
from .prompts import PromptLibrary

__all__ = [
    "DshHeadlessClient",
    "PromptLibrary",
    "BatchResult",
    "LlmError",
    "LlmTimeoutError",
    "LlmProcessError",
    "LlmParseError",
    "LlmEnvironmentError",
    "extract_json",
    "find_node",
    "find_dsh_entry",
]
