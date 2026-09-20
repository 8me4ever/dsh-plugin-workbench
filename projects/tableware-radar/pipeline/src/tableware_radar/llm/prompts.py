"""阶段 A / 阶段 C Prompt 模板库（docs/ARCHITECTURE.md §1.3 / §5）。

两条独立方法论对应两份独立 Prompt（D3）：

* **阶段 A（开放编码）**：只做 ``claim + topic_phrase`` 的**自由发现**，
  **严禁**把评论归类到既有维度——维度尚未固化，归类会污染发现。
* **阶段 C（封闭打标）**：只在 ``config/dimensions.yaml`` 的**封闭枚举**内打标，
  每条必备 ``evidence``（英文原文、不翻译）与 ``dimension_name``（中文名）；
  无匹配则用 ``OTHER`` + 自由话题短语。

统一输出约定（§7「JSON 输出」）：**只输出 JSON、无 prose、无 markdown fence、不用工具**。
Python 侧再做一次健壮抽取（``client.extract_json``）。
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from .. import config
from ..models import Dimension

__all__ = ["PromptLibrary"]


class PromptLibrary:
    """Prompt 模板库。``prompt_version`` 会写进每条 ``labeling.prompt_version``。"""

    prompt_version: str = config.PROMPT_VERSION

    # 通用输出约定（附在所有任务结尾）。
    _OUTPUT_CONTRACT = (
        "OUTPUT CONTRACT (must follow strictly):\n"
        "- Return ONLY a compact JSON array. No prose, no explanation, no markdown fences, no tools.\n"
        "- Do not wrap the array in an object. The first character must be '[' and the last must be ']'.\n"
        "- Every string value must be valid JSON (escape quotes/newlines).\n"
    )

    # ------------------------------------------------------------------ #
    # 阶段 A：开放编码
    # ------------------------------------------------------------------ #
    def build_stage_a(self, batch: Sequence[dict[str, Any]]) -> str:
        """构造阶段 A 任务：对一批评论做**开放式**话题发现。

        ``batch`` 元素需含 ``review_id`` / ``title`` / ``body``。
        期望输出（与 ``batch`` **等长、顺序一致**）：
        ``[{claim_text, topic_phrase, sentiment, source_review_id}]``
        """
        payload = [
            {
                "review_id": str(item.get("review_id", "")),
                "title": str(item.get("title", "")),
                "body": str(item.get("body", "")),
            }
            for item in batch
        ]
        example = json.dumps(
            [
                {
                    "claim_text": "the plates chipped after a few dishwasher cycles",
                    "topic_phrase": "dishwasher durability",
                    "sentiment": "neg",
                    "source_review_id": "R12345678",
                }
            ],
            ensure_ascii=False,
        )
        return (
            "You are a product-review analyst doing OPEN CODING for a UK tableware (plates & bowls) study.\n"
            "For EACH review below, extract the main claim(s) the customer makes and label the free-form topic.\n\n"
            "RULES:\n"
            "- Do NOT classify into any predefined category. There is no category list. Only discover topics.\n"
            "- For every review emit exactly ONE object (the dominant claim). Keep the same order as input.\n"
            "- `claim_text`: a short English paraphrase of what the reviewer claims (<=200 chars).\n"
            "- `topic_phrase`: a short English noun phrase for the topic (2-5 words, lowercase).\n"
            "- `sentiment`: one of pos | neg | neutral | mixed.\n"
            "- `source_review_id`: copy the review's `review_id` exactly.\n\n"
            f"EXAMPLE OUTPUT: {example}\n\n"
            f"INPUT REVIEWS ({len(payload)}):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"{self._OUTPUT_CONTRACT}"
        )

    # ------------------------------------------------------------------ #
    # 阶段 C：封闭打标
    # ------------------------------------------------------------------ #
    def build_stage_c(self, batch: Sequence[dict[str, Any]], dimensions: Sequence[Dimension]) -> str:
        """构造阶段 C 任务：在**封闭枚举**内逐条评论打标。

        ``batch`` 元素需含 ``review_id`` / ``title`` / ``body``。
        期望输出（与 ``batch`` **等长、顺序一致**）：
        ``[{review_id, labels:[{dimension, dimension_name, value, polarity, confidence, evidence}]}]``
        """
        payload = [
            {
                "review_id": str(item.get("review_id", "")),
                "title": str(item.get("title", "")),
                "body": str(item.get("body", "")),
            }
            for item in batch
        ]
        dimension_block = self._render_dimensions(dimensions)
        example = json.dumps(
            [
                {
                    "review_id": "R12345678",
                    "labels": [
                        {
                            "dimension": "DUR",
                            "dimension_name": "耐用性",
                            "value": "chips_easily",
                            "polarity": "neg",
                            "confidence": 0.86,
                            "evidence": "one of them had a small chip on the rim",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        )
        return (
            "You are a product-review analyst doing CLOSED-CODE LABELING for a UK tableware study.\n"
            "Assign labels to each review using ONLY the dimensions and enum values listed below.\n\n"
            f"DIMENSIONS:\n{dimension_block}\n\n"
            "RULES:\n"
            "- For every review emit exactly ONE object, in the same order as input, keyed by `review_id`.\n"
            "- `labels` is an array; include a label only when the review actually supports it.\n"
            "- `dimension` MUST be one of the listed IDs. `value` MUST be one of that dimension's enum values.\n"
            "- `dimension_name` MUST be the Chinese display name of the chosen dimension (copy verbatim).\n"
            "- `polarity` is one of pos | neg | neutral | mixed.\n"
            "- `confidence` is a number in [0,1].\n"
            "- `evidence` MUST be an English substring quoted from the review (<=160 chars). NEVER translate it.\n"
            "- If nothing fits, use dimension 'OTHER' and put a short free-form English topic phrase in `value`.\n"
            "- Do NOT invent dimensions or values that are not listed.\n\n"
            f"EXAMPLE OUTPUT: {example}\n\n"
            f"INPUT REVIEWS ({len(payload)}):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"{self._OUTPUT_CONTRACT}"
        )

    def build_repair(
        self,
        stage: str,
        batch: Sequence[dict[str, Any]],
        error: str,
        previous_output: str = "",
        dimensions: Sequence[Dimension] | None = None,
    ) -> str:
        """构造「修复式」重试任务（由 batch 重建原始 task）。

        ``stage`` ∈ ``{"a", "c"}``。若手上已有原始 task 文本，直接用
        ``build_repair_from_task`` —— 那才是客户端的 ``repair`` 回调拿得到的入参。
        """
        base = (
            self.build_stage_c(batch, dimensions or [])
            if stage == "c"
            else self.build_stage_a(batch)
        )
        return self.build_repair_from_task(stage, base, error, previous_output)

    def build_repair_from_task(
        self,
        stage: str,
        task: str,
        error: str,
        previous_output: str = "",
    ) -> str:
        """修复式重试：把**原始 task 文本**原样附回，只要求补正、不发明。

        与 ``build_repair`` 的区别是入参是已经拼好的 task，因此可以当作
        ``DshHeadlessClient.run_batch(repair=...)`` 的回调使用（该回调签名是
        ``(task, error, previous_output)``，拿不到 batch）。
        """
        return (
            "Your previous answer was REJECTED.\n"
            f"REJECTION REASON: {error}\n"
            "Fix ONLY what is required to satisfy the rules. Do NOT add new items, "
            "invent dimensions, or change the number of objects. Keep the same order.\n"
            f"YOUR PREVIOUS OUTPUT (truncated):\n{previous_output[:800]}\n\n"
            f"--- ORIGINAL TASK BELOW ---\n{task}"
        )

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _render_dimensions(self, dimensions: Sequence[Dimension]) -> str:
        if not dimensions:
            return "(no dimensions configured)"
        lines: list[str] = []
        for dim in dimensions:
            values = ", ".join(dim.values) if dim.values else "(any free-form short phrase)"
            lines.append(
                f"- {dim.id} | name: {dim.name} | definition: {dim.definition or '-'}\n"
                f"    allowed values: {values}"
            )
        return "\n".join(lines)
