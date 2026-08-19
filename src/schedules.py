# -*- coding: utf-8 -*-
"""官方赛事"往届经验"报名日程表。

用于拿不到当年官方报名日期时的兜底推断，推断结果一律标注"（按往届）"。
口径（按用户要求）：
  - 官方赛事必须有报名时间信息：有真实截止日期最好；
    没有时按往届经验推断报名窗口；
  - 本届报名窗口已过 → 不展示（从表里移除）；
  - 可推断出下一窗口 → 保留并写明"预计X月启动报名（按往届）"；
  - 查不到往届规律 → 不展示（不再出现"待核实"）。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 每年报名月份列表（按往年规律整理，月份可跨年）
DEFAULT_SCHEDULES: List[Dict[str, Any]] = [
    {"keywords": ["蓝桥杯"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["数学建模"], "months": [6, 7, 8, 9]},
    {"keywords": ["国际大学生创新", "大学生创新创业"], "months": [3, 4, 5]},
    {"keywords": ["挑战杯"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["计算机设计大赛"], "months": [11, 12, 1, 2, 3, 4]},
    {"keywords": ["信息安全竞赛"], "months": [3, 4, 5, 6]},
    {"keywords": ["天梯赛"], "months": [11, 12, 1, 2, 3]},
    {"keywords": ["中国软件杯", "软件杯"], "months": [4, 5, 6, 7]},
    {"keywords": ["服务外包"], "months": [3, 4, 5, 6]},
    {"keywords": ["智能汽车", "智能车"], "months": [1, 2, 3, 4, 5]},
    {"keywords": ["RoboMaster", "机器人大赛"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["华为ICT"], "months": [9, 10, 11]},
    {"keywords": ["金砖"], "months": [3, 4, 5, 6, 7]},
    {"keywords": ["创客中国"], "months": [4, 5, 6, 7, 8]},
    {"keywords": ["电子设计"], "months": [3, 4, 5, 6, 7]},
    {"keywords": ["集成电路"], "months": [1, 2, 3, 4, 5]},
    {"keywords": ["物联网设计"], "months": [3, 4, 5, 6]},
]


def get_schedules(config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    cfg = config or {}
    custom = cfg.get("official_schedules")
    if isinstance(custom, list) and custom:
        return custom
    return DEFAULT_SCHEDULES


def enrich_official(
    title: str,
    deadline: str = "",
    config: Dict[str, Any] = None,
    today: Optional[datetime] = None,
) -> Tuple[str, bool]:
    """官方赛事报名时间推断。

    返回 (报名说明, 是否保留)。说明如："报名中（按往届）"、"预计10月启动报名（按往届）"。
    无法推断或本届已过时 keep=False（从表中移除，不写"待核实"）。
    """
    t = title or ""
    if deadline:
        return "", True  # 有真实截止日期，直接用
    today = today or datetime.now()
    for entry in get_schedules(config):
        if not any(k in t for k in entry.get("keywords", [])):
            continue
        months = [int(m) for m in entry.get("months", [])]
        if not months:
            return "", False
        now_month = today.month
        now_year = today.year
        # 标题里的届次年份（如 "2026年蓝桥杯"）
        m = re.search(r"(20\d{2})", t)
        title_year = int(m.group(1)) if m else None

        in_window = now_month in months
        if not in_window:
            # 本届（标题年份）报名窗口已过 → 移除
            if title_year is not None and title_year <= now_year:
                return "", False
            next_m = min((x for x in months if x > now_month), default=months[0])
            return f"预计{next_m}月启动报名（按往届）", True
        # 窗口内
        if title_year is not None and title_year < now_year:
            return "", False  # 往届条目
        return "报名中（按往届）", True
    return "", False  # 查不到往届规律 → 不展示
