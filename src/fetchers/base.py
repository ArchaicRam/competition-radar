# -*- coding: utf-8 -*-
"""抓取器基类"""
from __future__ import annotations

from typing import Any, Dict, List

from ..models import Competition


class FetcherSkip(Exception):
    """抓取器主动跳过（如未配置必要账号），不算错误。"""


class BaseFetcher:
    """所有平台抓取器的基类。

    子类实现 fetch()，返回 Competition 列表。
    约定：抓取失败应抛出异常，由 runner 统一捕获记录，
    不要吞掉异常返回空列表（否则会误报"无比赛"）。
    """

    platform: str = "base"

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def fetch(self) -> List[Competition]:
        raise NotImplementedError

    def _timeout(self) -> int:
        return int(self.cfg.get("http_timeout", 30))

    def _headers(self, extra: Dict[str, str] | None = None) -> Dict[str, str]:
        h = {
            "User-Agent": self.cfg.get("user_agent", ""),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if extra:
            h.update(extra)
        return h
