# -*- coding: utf-8 -*-
"""官方赛事"往届经验"报名日程表 —— 【已停用，仅作参考，勿再用于生成日期】。

⚠️ 2026-11 改造后 runner 已不再调用 enrich_official()。
   原因：用月份表推算"预计X月启动报名"，会被下游渲染成"报名中"，
   等于把"还没开报名"说成"能报名"。实测反例：
     · 蓝桥杯第十八届真实报名截止 2026-12-18，月份表只知道"10月-次年3月"；
     · 美赛官网开到 2027-01-28，但多数学校校内 11 月就关了。
   现在的口径是：查不到就写"未公布"，由 jwc / 官网源去补真值。
   本文件的 months 数据仅在需要"提醒该关注了"时参考，**绝不可写入 deadline 或 status**。

原始说明（保留）：用于拿不到当年官方报名日期时的兜底推断，推断结果标注"（按往届）"。
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
    # 学校竞赛目录补漏（按往届规律估算）
    {"keywords": ["工程实践与创新能力"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["程序设计竞赛"], "months": [6, 7, 8, 9, 10]},
    {"keywords": ["嵌入式"], "months": [3, 4, 5, 6]},
    {"keywords": ["智能机器人", "机器人及人工智能"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["RoboCom"], "months": [4, 5, 6, 7, 8]},
    {"keywords": ["大唐杯"], "months": [3, 4, 5]},
    {"keywords": ["青年创客"], "months": [4, 5, 6]},
    {"keywords": ["BIM"], "months": [10, 11, 12, 1, 2, 3]},
    {"keywords": ["西门子杯"], "months": [3, 4, 5, 6]},
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
