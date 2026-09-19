"""pytest 全局夹具与路径引导。

``pytest.ini`` 已通过 ``pythonpath = src`` 注入源码路径；此处再显式兜底一次，
使得即便用 ``python -m pytest`` 之外的入口运行也能导入 ``tableware_radar``。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
