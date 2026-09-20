"""``dimensions.yaml`` 加载与校验（docs/ARCHITECTURE.md §5 T06）。

维度体系是**阶段 C 封闭打标的唯一枚举真源**。本模块：

* ``DimensionSet.load(path)`` 解析 YAML → ``Dimension`` 集合；
* ``DimensionSet.validate()`` 拒绝不合规配置：
  - 缺枚举（某维 ``values`` 为空）；
  - 漏标排除项（``SCN``/``SAF`` 未标 ``excluded_from_opportunity: true``，
    或评分维度被误标为排除）；
  - 引用未定义枚举（``validate_label`` 拒绝未在该维 ``values`` 中的值；
    ``OTHER`` 为合法开放逃生口）；
  - 缺四要素（definition / judgement / values / 正负例句）、缺版本号、重复维度、非法枚举命名。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

from . import config
from .models import Dimension

__all__ = [
    "DimensionError",
    "REQUIRED_DIMENSION_IDS",
    "EXCLUDED_FROM_OPPORTUNITY_IDS",
    "DimensionSet",
    "load_dimension_set",
]

# PRD §4.2 的 10 个维度（既定全集，勿删）。
REQUIRED_DIMENSION_IDS: tuple[str, ...] = (
    "DUR", "CLE", "AES", "SIZ", "PCK", "SCN", "STR", "HAN", "VAL", "SAF",
)

# 不参与机会分排序的维度（SCN 只进 filters、SAF 只进 risk_flags，见 §4.4）。
EXCLUDED_FROM_OPPORTUNITY_IDS: frozenset[str] = frozenset({"SCN", "SAF"})

# 阶段 C 的开放逃生口（不属任何维度枚举）。
OTHER_DIMENSION_ID = "OTHER"

_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_VALUE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class DimensionError(ValueError):
    """维度体系不合规。"""


@dataclass
class DimensionSet:
    """维度集合（阶段 C 枚举真源）。"""

    version: str
    by_id: dict[str, Dimension] = field(default_factory=dict)
    source_path: str = ""

    # ---- 加载 ----
    @classmethod
    def load(cls, path: str | Path | None = None) -> "DimensionSet":
        path = Path(path) if path is not None else config.DIMENSIONS_PATH
        if not path.exists():
            raise DimensionError(
                f"dimensions.yaml 不存在：{path}\n"
                f"请复制模板开始固化：copy \"{config.DIMENSIONS_EXAMPLE_PATH}\" \"{config.DIMENSIONS_PATH}\""
            )
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise DimensionError(f"dimensions.yaml 解析失败：{exc}") from exc
        if not isinstance(data, dict):
            raise DimensionError("dimensions.yaml 顶层必须是映射（含 version / dimensions）。")

        version = str(data.get("version", "") or "")
        raw_dims = data.get("dimensions", [])
        if not isinstance(raw_dims, list):
            raise DimensionError("dimensions 必须是列表。")

        by_id: dict[str, Dimension] = {}
        for entry in raw_dims:
            if not isinstance(entry, dict):
                raise DimensionError(f"维度项必须是映射，实得：{entry!r}")
            dim = Dimension.from_dict(entry)
            dim.version = dim.version or version or config.DIMENSION_SET_VERSION
            if dim.id in by_id:
                raise DimensionError(f"重复的维度 id：{dim.id}")
            by_id[dim.id] = dim

        return cls(version=version or config.DIMENSION_SET_VERSION, by_id=by_id, source_path=str(path))

    # ---- 校验 ----
    def validate(self, *, require_all: bool = True) -> None:
        """校验是否可作为阶段 C 的枚举真源。不合规则抛 ``DimensionError``。"""
        if not self.version:
            raise DimensionError("缺少 version。")
        if not self.by_id:
            raise DimensionError("dimensions 为空。")

        for dim_id, dim in self.by_id.items():
            self._validate_one(dim_id, dim)

        if require_all:
            missing = [d for d in REQUIRED_DIMENSION_IDS if d not in self.by_id]
            if missing:
                raise DimensionError(f"缺少必需维度：{', '.join(missing)}")

        # 排除项必须与 EXCLUDED_FROM_OPPORTUNITY_IDS 一致（既查漏标，也查误标）。
        for expected_excluded in EXCLUDED_FROM_OPPORTUNITY_IDS:
            dim = self.by_id.get(expected_excluded)
            if dim is not None and not dim.excluded_from_opportunity:
                raise DimensionError(
                    f"{expected_excluded} 必须 excluded_from_opportunity: true（否则会错误进入机会分排序）。"
                )
        for dim_id, dim in self.by_id.items():
            if dim_id not in EXCLUDED_FROM_OPPORTUNITY_IDS and dim.excluded_from_opportunity:
                raise DimensionError(
                    f"{dim_id} 不应 excluded_from_opportunity: true（评分维度必须参与机会分排序）。"
                )

    @staticmethod
    def _validate_one(dim_id: str, dim: Dimension) -> None:
        if not _ID_RE.match(dim.id):
            raise DimensionError(f"非法维度 id（应为大写）：{dim.id!r}")
        if not dim.name:
            raise DimensionError(f"{dim_id} 缺少 name（中文显示名）。")
        if not dim.definition:
            raise DimensionError(f"{dim_id} 缺少 definition。")
        if not dim.judgement:
            raise DimensionError(f"{dim_id} 缺少 judgement（判定依据）。")
        if not dim.values:
            raise DimensionError(f"{dim_id} 缺少枚举（values 为空）。")
        if not dim.positive_examples and not dim.negative_examples:
            raise DimensionError(f"{dim_id} 至少需要一个正/负极性例句。")
        seen: set[str] = set()
        for value in dim.values:
            if not _VALUE_RE.match(value):
                raise DimensionError(f"{dim_id} 的枚举值命名非法（应为小写下划线）：{value!r}")
            if value in seen:
                raise DimensionError(f"{dim_id} 存在重复枚举值：{value!r}")
            seen.add(value)

    # ---- 查询 ----
    def get(self, dimension_id: str) -> Optional[Dimension]:
        return self.by_id.get(dimension_id)

    def ids(self) -> list[str]:
        return list(self.by_id.keys())

    def scoring_ids(self) -> list[str]:
        """参与机会分排序的维度（排除 SCN/SAF）。"""
        return [d for d in self.by_id if d not in EXCLUDED_FROM_OPPORTUNITY_IDS]

    def value_exists(self, dimension_id: str, value: str) -> bool:
        dim = self.by_id.get(dimension_id)
        return dim is not None and value in dim.values

    def validate_label(self, dimension_id: str, value: str) -> None:
        """校验单个标签是否引用**已定义枚举**（阶段 C 用）。

        ``OTHER`` 维度豁免（其 ``value`` 为自由话题短语）；否则拒绝未定义枚举。
        不合规抛 ``DimensionError``。
        """
        if dimension_id == OTHER_DIMENSION_ID:
            if not value:
                raise DimensionError("OTHER 维度必须带自由话题短语作为 value。")
            return
        dim = self.by_id.get(dimension_id)
        if dim is None:
            raise DimensionError(f"引用了未定义维度：{dimension_id!r}")
        if value not in dim.values:
            raise DimensionError(
                f"引用了未定义枚举：{dimension_id}/{value!r}（合法值：{', '.join(dim.values)}）"
            )

    def name_of(self, dimension_id: str) -> str:
        dim = self.by_id.get(dimension_id)
        return dim.name if dim else ""


def load_dimension_set(path: str | Path | None = None, *, validate: bool = True) -> DimensionSet:
    """加载并（默认）校验维度集合。"""
    dimension_set = DimensionSet.load(path)
    if validate:
        dimension_set.validate()
    return dimension_set
