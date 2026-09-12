# -*- coding: utf-8 -*-
"""飞书在线表格同步（通过 lark-cli 官方 CLI 调用）。

用法前提：
  - lark-cli 已安装，且配置了应用 profile（如 jingsai）
  - 应用已开通 sheets/drive 权限（bot 身份即可，无需用户登录）
  - 表格已创建，把 URL 填进 config.json 的 feishu_sheet_url

同步策略（每次运行全量重写，保证"今日新增"高亮干净）：
  清空 -> 写数据 -> 表头样式 -> 新增行红底 -> 列宽
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Dict, List, Optional, Set

from . import lark as lark_mod
from .models import Competition
from .official import categorize, clean_text, normalize_comp_type, prestige
from .platforms import PLATFORM_NAMES

log = logging.getLogger("feishu_sheet")


_HEADERS = ["类别", "含金量", "赛名", "主办方", "类型", "开始日期", "截止日期", "阶段", "奖金", "来源", "链接"]
_COL_WIDTHS = {"A": 90, "B": 80, "C": 260, "D": 180, "E": 90, "F": 130, "G": 130, "H": 80, "I": 110, "J": 90, "K": 320}
_MAX_ROWS = 1000
_LAST_COL = "K"

# 含金量条件格式：高=红、中=橙、低=绿（整列一条规则，无需逐行样式）
_RATING_RULES = [
    ("高", "#E02020"),
    ("中", "#E67E22"),
    ("低", "#2ECC40"),
]


def sync_sheet(
    comps: List[Competition],
    new_keys: Set[str],
    sheet_url: str,
    profile: str = "jingsai",
    sheet_name: str = "Sheet1",
) -> str:
    """把比赛列表全量同步到飞书在线表格，返回表格 URL。"""
    csv_text = _build_csv(comps)
    args = ["--profile", profile, "sheets"]

    # 1. 清空旧数据（含格式，昨日的新增高亮一并清掉）
    #    注：+cells-clear 是飞书 high-risk-write，需 --yes；
    #        已获用户明确授权（仅针对本系统的竞赛总览表）。
    lark_mod.lark(args + ["+cells-clear", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--range", f"A1:{_LAST_COL}{_MAX_ROWS}", "--scope", "all", "--yes"])

    # 2. 写入数据
    lark_mod.lark(args + ["+csv-put", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--start-cell", "A1", "--csv", "-"], stdin_text=csv_text)

    # 3. 表头样式
    lark_mod.lark(args + ["+cells-set-style", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--range", f"A1:{_LAST_COL}1", "--font-weight", "bold",
                  "--background-color", "#D9D9D9", "--horizontal-alignment", "center"])

    # 4. 今日新增行红底红字（相邻新增行合并成区间，减少 lark-cli 调用次数）
    runs: List[List[int]] = []
    for i, c in enumerate(comps, start=2):
        if c.key in new_keys:
            if runs and runs[-1][1] == i - 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
    for start, end in runs:
        rng = f"A{start}:{_LAST_COL}{end}"
        lark_mod.lark(args + ["+cells-set-style", "--url", sheet_url, "--sheet-name", sheet_name,
                      "--range", rng, "--background-color", "#FFC7CE",
                      "--font-color", "#9C0006"])

    # 5. 列宽
    lark_mod.lark(args + ["+cols-resize", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--widths", json.dumps(_COL_WIDTHS)])

    # 6. 含金量列颜色（条件格式，整列一条规则；已存在则不重复建）
    _ensure_rating_rules(args, sheet_url, sheet_name)
    log.info("飞书在线表格已同步: %s（%d 行，今日新增 %d）", sheet_url, len(comps), len(new_keys))
    return sheet_url


def _ensure_rating_rules(args, sheet_url, sheet_name):
    """给含金量列 B 加条件格式：高=红、中=橙、低=绿（缺哪条补哪条）。"""
    existing = set()
    try:
        resp = lark_mod.lark(args + ["+cond-format-list", "--url", sheet_url, "--sheet-name", sheet_name])
        for s in (resp.get("data") or {}).get("sheets") or []:
            for r in s.get("conditional_formats") or []:
                for a in (r.get("details") or {}).get("attrs") or []:
                    if a.get("compare_type") == "containsText" and a.get("text"):
                        existing.add(a["text"])
    except Exception:  # noqa: BLE001
        pass
    for text, color in _RATING_RULES:
        if text in existing:
            continue
        style = {"fore_color": color}
        if text == "高":
            style["font"] = "bold"  # 枚举只支持 bold/italic，普通样式不传
        props = {
            "attrs": [{"compare_type": "containsText", "text": text}],
            "style": style,
        }
        lark_mod.lark(args + ["+cond-format-create", "--url", sheet_url, "--sheet-name", sheet_name,
                      "--rule-type", "containsText",
                      "--ranges", json.dumps([f"B2:B{_MAX_ROWS}"]),
                      "--properties", json.dumps(props, ensure_ascii=False)])


def _build_csv(comps: List[Competition]) -> str:
    buf = io.StringIO()
    # lineterminator 用 \n：飞书 CSV 解析器会把 \r 和 \n 都当行分隔，
    # 用 CRLF 会导致隔行出现空行
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(_HEADERS)
    for c in comps:
        w.writerow([
            categorize(c.title, c.organizer, c.platform),
            prestige(c.title, c.organizer, c.platform, c.rating),
            clean_text(c.title),
            clean_text(c.organizer),
            normalize_comp_type(c.comp_type),
            c.enabled_date,
            c.deadline,
            c.status,
            c.reward,
            PLATFORM_NAMES.get(c.platform, c.platform),
            c.url,
        ])
    return buf.getvalue()
