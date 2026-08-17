# -*- coding: utf-8 -*-
"""抓取器注册表：按平台名构建对应抓取器。"""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseFetcher
from .datafountain import DataFountainFetcher

# 各平台抓取器会随探测结果逐步加入
try:
    from .kaggle import KaggleFetcher
except ImportError:  # 尚未实现时保持可导入
    KaggleFetcher = None  # type: ignore[assignment]

try:
    from .tianchi import TianchiFetcher
except ImportError:
    TianchiFetcher = None  # type: ignore[assignment]

try:
    from .nowcoder import NowcoderFetcher
except ImportError:
    NowcoderFetcher = None  # type: ignore[assignment]

try:
    from .xfyun import XfyunFetcher
except ImportError:
    XfyunFetcher = None  # type: ignore[assignment]

try:
    from .saikr import SaikrFetcher
except ImportError:
    SaikrFetcher = None  # type: ignore[assignment]

_REGISTRY: Dict[str, type] = {
    "datafountain": DataFountainFetcher,
}
for _name, _cls in [
    ("kaggle", KaggleFetcher),
    ("tianchi", TianchiFetcher),
    ("nowcoder", NowcoderFetcher),
    ("xfyun", XfyunFetcher),
    ("saikr", SaikrFetcher),
]:
    if _cls is not None:
        _REGISTRY[_name] = _cls


def build(name: str, cfg: Dict[str, Any]) -> BaseFetcher:
    if name not in _REGISTRY:
        raise ValueError(f"未知平台: {name}，可用: {sorted(_REGISTRY)}")
    return _REGISTRY[name](cfg)
