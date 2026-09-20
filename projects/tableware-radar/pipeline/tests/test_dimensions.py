"""T06 验收测试：dimensions.yaml 加载与校验。

覆盖：覆盖全部 10 维、四要素完整性、SCN/SAF 排除项、validate() 拒绝
「缺枚举 / 漏标排除项 / 误标排除 / 缺维度 / 非法命名」，以及 validate_label 拒绝未定义枚举。
"""

from __future__ import annotations

import copy

import pytest
import yaml

from tableware_radar import config
from tableware_radar.dimensions import (
    EXCLUDED_FROM_OPPORTUNITY_IDS,
    REQUIRED_DIMENSION_IDS,
    DimensionError,
    DimensionSet,
    load_dimension_set,
)


def _example_data() -> dict:
    return yaml.safe_load(config.DIMENSIONS_EXAMPLE_PATH.read_text(encoding="utf-8"))


def _write(tmp_path, data: dict):
    path = tmp_path / "dimensions.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _dim(data: dict, dim_id: str) -> dict:
    return next(d for d in data["dimensions"] if d["id"] == dim_id)


# --------------------------------------------------------------------------- #
# 正常加载
# --------------------------------------------------------------------------- #

def test_example_loads_and_validates():
    dims = load_dimension_set(config.DIMENSIONS_EXAMPLE_PATH)
    assert dims.version.startswith("dims-")
    for required in REQUIRED_DIMENSION_IDS:
        assert required in dims.by_id


def test_real_dimensions_yaml_covers_all_ten():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    assert set(REQUIRED_DIMENSION_IDS).issubset(set(dims.ids()))
    assert len(dims.ids()) >= 10


def test_scn_and_saf_excluded_others_not():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    for dim_id in EXCLUDED_FROM_OPPORTUNITY_IDS:
        assert dims.get(dim_id).excluded_from_opportunity is True
    for dim_id in dims.ids():
        if dim_id not in EXCLUDED_FROM_OPPORTUNITY_IDS:
            assert dims.get(dim_id).excluded_from_opportunity is False
    # 参与机会分的维度 = 10 - 2
    assert set(dims.scoring_ids()) == set(REQUIRED_DIMENSION_IDS) - EXCLUDED_FROM_OPPORTUNITY_IDS


# --------------------------------------------------------------------------- #
# 校验拒绝
# --------------------------------------------------------------------------- #

def test_validate_rejects_missing_enumeration(tmp_path):
    data = _example_data()
    _dim(data, "DUR")["values"] = []
    with pytest.raises(DimensionError, match="缺.*枚举"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_validate_rejects_uncapped_scn(tmp_path):
    data = _example_data()
    _dim(data, "SCN")["excluded_from_opportunity"] = False
    with pytest.raises(DimensionError, match="SCN"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_validate_rejects_wrongly_excluded_scoring_dim(tmp_path):
    data = _example_data()
    _dim(data, "DUR")["excluded_from_opportunity"] = True
    with pytest.raises(DimensionError, match="DUR"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_validate_rejects_missing_required_dimension(tmp_path):
    data = _example_data()
    data["dimensions"] = [d for d in data["dimensions"] if d["id"] != "SAF"]
    with pytest.raises(DimensionError, match="缺少必需维度"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_validate_rejects_missing_definition(tmp_path):
    data = _example_data()
    _dim(data, "CLE")["definition"] = ""
    with pytest.raises(DimensionError, match="definition"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_validate_rejects_illegal_enum_name(tmp_path):
    data = _example_data()
    _dim(data, "VAL")["values"] = ["GoodValue"]      # 大写非法
    with pytest.raises(DimensionError, match="命名非法"):
        DimensionSet.load(_write(tmp_path, data)).validate()


def test_load_rejects_duplicate_dimension(tmp_path):
    data = _example_data()
    data["dimensions"].append(copy.deepcopy(_dim(data, "DUR")))
    with pytest.raises(DimensionError, match="重复"):
        DimensionSet.load(_write(tmp_path, data))


def test_load_missing_file_raises_with_hint(tmp_path):
    with pytest.raises(DimensionError, match="不存在"):
        DimensionSet.load(tmp_path / "nope.yaml")


def test_load_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(DimensionError, match="映射"):
        DimensionSet.load(path)


# --------------------------------------------------------------------------- #
# validate_label：引用未定义枚举
# --------------------------------------------------------------------------- #

def test_validate_label_accepts_defined_value():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    dims.validate_label("DUR", "chips_easily")       # 不抛即通过
    assert dims.value_exists("DUR", "chips_easily") is True


def test_validate_label_rejects_undefined_value():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    with pytest.raises(DimensionError, match="未定义枚举"):
        dims.validate_label("DUR", "not_a_real_value")


def test_validate_label_rejects_unknown_dimension():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    with pytest.raises(DimensionError, match="未定义维度"):
        dims.validate_label("XYZ", "whatever")


def test_validate_label_allows_other():
    dims = load_dimension_set(config.DIMENSIONS_PATH)
    dims.validate_label("OTHER", "delivery packaging")
    with pytest.raises(DimensionError):
        dims.validate_label("OTHER", "")
