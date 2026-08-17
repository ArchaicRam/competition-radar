# -*- coding: utf-8 -*-
"""科大讯飞 AI 开发者大赛（challenge.xfyun.cn）抓取器。

API 已实测（GET）：
  /2020/ai-contest/api/contests/contests-list      —— 全部赛事（含历史）
  /2020/ai-contest/api/contests/edu-contests-list  —— 教育类赛事
返回 {"flag":true,"code":0,"data":[...]}，data 内每项字段带 _basic_problem 后缀。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .. import http
from ..models import Competition
from .base import BaseFetcher


class XfyunFetcher(BaseFetcher):
    platform = "xfyun"
    APIS = [
        "https://challenge.xfyun.cn/2020/ai-contest/api/contests/contests-list",
        "https://challenge.xfyun.cn/2020/ai-contest/api/contests/edu-contests-list",
    ]

    def fetch(self) -> List[Competition]:
        out: List[Competition] = []
        for api in self.APIS:
            data = http.get_json(
                api,
                headers=self._headers({"Referer": "https://challenge.xfyun.cn/"}),
                timeout=self._timeout(),
            )
            for d in data.get("data") or []:
                c = self._convert(d)
                if c is not None:
                    out.append(c)
        return out

    def _convert(self, d: dict) -> Optional[Competition]:
        name = (d.get("name_basic_problem") or "").strip()
        if not name:
            return None
        flag = (d.get("contest_flag") or "").strip()
        register_end = _clean_date(d.get("registerEnd_basic_problem"))
        prelim_end = _clean_date(d.get("prelimEnd_basic_problem"))
        deadline = register_end or prelim_end

        # 已结束的赛事不推
        status = _status(register_end, prelim_end)
        if status == "已结束":
            return None
        bonus = (d.get("bonus_basic_problem") or "").strip()
        reward = f"¥{bonus}万" if bonus and _is_number(bonus) else bonus
        url = f"https://challenge.xfyun.cn/topic/info?type={flag}" if flag else (d.get("external_link") or "")
        return Competition(
            key=f"xfyun:{flag or name}",
            title=name,
            platform=self.platform,
            organizer=(d.get("sponsorName_basic_problem") or "").strip(),
            url=url,
            deadline=deadline,
            reward=reward,
            comp_type=(d.get("type_basic_problem") or d.get("industry") or "").strip(),
            status=status,
            enabled_date=_clean_date(d.get("registerBegin_basic_problem")),
        )


def _clean_date(v) -> str:
    """占位日期（如 1999-09-09）视为空。"""
    s = (str(v) if v is not None else "").strip()
    if s in ("", "null", "1999-09-09", "0000-00-00"):
        return ""
    return s[:10]


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_past(date_str: str) -> bool:
    s = (date_str or "").strip()
    if not s or s == "1999-09-09":
        return False
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d") < datetime.now()
    except ValueError:
        return False


def _status(register_end: str, prelim_end: str) -> str:
    reg_end = (register_end or "").strip()
    if reg_end and not _is_past(reg_end):
        return "报名中"
    if prelim_end and not _is_past(prelim_end):
        return "进行中"
    if reg_end or prelim_end:
        return "已结束"
    return "待定"  # 无有效日期
