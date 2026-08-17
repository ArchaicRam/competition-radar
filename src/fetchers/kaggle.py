# -*- coding: utf-8 -*-
"""Kaggle 抓取器。

Kaggle 的公开列表 API（/api/v1/competitions/list）需要 Kaggle 账号认证：
  - 注册 https://www.kaggle.com 后，在 Settings -> API 里 Create New Token，
    得到 kaggle.json（含 username 和 key）
  - 把 username/key 填进 config.json 的 kaggle_username / kaggle_key，
    或在环境变量 KAGGLE_USERNAME / KAGGLE_KEY 中配置
未配置时本抓取器跳过（不报错）。
"""
from __future__ import annotations

import base64
import os
from typing import List

from .. import http
from ..models import Competition
from .base import BaseFetcher, FetcherSkip


class KaggleFetcher(BaseFetcher):
    platform = "kaggle"
    LIST_API = "https://www.kaggle.com/api/v1/competitions/list"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.username = (cfg.get("kaggle_username") or "").strip() or os.environ.get("KAGGLE_USERNAME", "").strip()
        self.key = (cfg.get("kaggle_key") or "").strip() or os.environ.get("KAGGLE_KEY", "").strip()

    def fetch(self) -> List[Competition]:
        if not (self.username and self.key):
            raise FetcherSkip(
                "未配置 Kaggle 账号（config.json 的 kaggle_username/kaggle_key 或环境变量 "
                "KAGGLE_USERNAME/KAGGLE_KEY），本次跳过 Kaggle"
            )
        token = base64.b64encode(f"{self.username}:{self.key}".encode("utf-8")).decode("ascii")
        data = http.get_json(
            self.LIST_API,
            headers=self._headers({"Authorization": f"Basic {token}", "Accept": "application/json"}),
            timeout=self._timeout(),
        )
        out: List[Competition] = []
        for item in data or []:
            c = self._convert(item)
            if c is not None:
                out.append(c)
        return out

    def _convert(self, item: dict):
        ref = (item.get("ref") or "").strip()
        title = (item.get("title") or "").strip()
        if not title:
            return None
        url = item.get("url") or ""
        if url.startswith("/"):
            url = "https://www.kaggle.com" + url
        elif not url.startswith("http"):
            url = f"https://www.kaggle.com/competitions/{ref}" if ref else ""
        deadline = (item.get("deadline") or "").strip()[:10]
        reward = (item.get("reward") or "").strip()
        organizer = (item.get("organizationName") or item.get("organizationRef") or "").strip()
        return Competition(
            key=f"kaggle:{ref or title}",
            title=title,
            platform=self.platform,
            organizer=organizer,
            url=url,
            deadline=deadline,
            reward=reward,
            comp_type=(item.get("category") or "").strip(),
            status="进行中" if not deadline or deadline >= _today() else "已结束",
            enabled_date=(item.get("enabledDate") or "").strip()[:10],
        )


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
