# -*- coding: utf-8 -*-
"""从 state.json 生成飞书表格 payload（联调/建表用）。"""
import json
import sys

sys.path.insert(0, r"D:\find_competition")

from src.models import Competition
from src.official import categorize, sort_competitions
from src.platforms import PLATFORM_NAMES

with open(r"D:\find_competition\data\state.json", encoding="utf-8") as f:
    state = json.load(f)

comps = [Competition.from_dict(d) for d in state["competitions"].values()]
comps = sort_competitions(comps)

headers = ["类别", "赛名", "主办方", "类型", "开始日期", "截止日期", "阶段", "奖金", "来源", "链接"]
rows = [
    [
        categorize(c.title, c.organizer, c.platform),
        c.title,
        c.organizer,
        c.comp_type,
        c.enabled_date,
        c.deadline,
        c.status,
        c.reward,
        PLATFORM_NAMES.get(c.platform, c.platform),
        c.url,
    ]
    for c in comps
]

if "--json" in sys.argv:
    print(json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False))
else:
    values = [headers] + rows
    print(json.dumps(values, ensure_ascii=False))
