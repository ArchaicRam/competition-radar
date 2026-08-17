# -*- coding: utf-8 -*-
"""赛氪（saikr.com）抓取器（暂未接入）。

赛氪前端是 Vite SPA，竞赛列表数据接口未公开（实测常见端点均 404），
且其内容以数学建模/英语/创新创业等综合竞赛为主，与"计算机企业赛"定位
重叠度低。后续若找到可用接口，在本文件实现 fetch() 即可。
"""
from __future__ import annotations

from typing import List

from ..models import Competition
from .base import BaseFetcher, FetcherSkip


class SaikrFetcher(BaseFetcher):
    platform = "saikr"

    def fetch(self) -> List[Competition]:
        raise FetcherSkip(
            "赛氪（saikr.com）竞赛列表接口未公开，暂未接入；"
            "可手动浏览 https://www.saikr.com/contests"
        )
