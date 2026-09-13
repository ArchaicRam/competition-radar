# -*- coding: utf-8 -*-
"""CSV 台账导出（Excel 可直接打开，utf-8-sig 带 BOM）。"""
from __future__ import annotations

import csv
import os

from .storage import Store
from .official import concrete_stage, normalize_comp_type, prestige

_COLUMNS = [
    "平台", "比赛名称", "主办方", "类型", "含金量", "报名截止", "开始日期",
    "奖金", "状态", "链接", "首次发现时间",
]


def export_csv(store: Store, path: str = "data/competitions.csv") -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(_COLUMNS)
        for d in store.all_sorted():
            w.writerow([
                d.get("platform", ""),
                d.get("title", ""),
                d.get("organizer", ""),
                normalize_comp_type(d.get("comp_type", "")),
                prestige(d.get("title", ""), d.get("organizer", ""), d.get("platform", ""), d.get("rating", "")),
                d.get("deadline", ""),
                d.get("enabled_date", ""),
                d.get("reward", ""),
                # 历史存量里可能有"待核实"，导出时统一规范成具体阶段
                concrete_stage(d.get("status", ""), d.get("deadline", "")),
                d.get("url", ""),
                d.get("detected_at", ""),
            ])
    return path
