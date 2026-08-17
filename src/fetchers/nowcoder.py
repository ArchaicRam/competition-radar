# -*- coding: utf-8 -*-
"""牛客（nowcoder.com）抓取器。

牛客"全网 OJ 比赛日历"官方接口（已实测可用，无需登录）：
  GET https://ac.nowcoder.com/acm/calendar/contest
返回 {"code":0,"msg":"OK","data":[{contestId, ojName, link, startTime, endTime, contestName}]}
覆盖牛客自家赛事 + AtCoder / Codeforces / LeetCode 等全网 OJ 算法赛，
对算法竞赛方向非常有价值。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .. import http
from ..models import Competition
from .base import BaseFetcher


class NowcoderFetcher(BaseFetcher):
    platform = "nowcoder"
    CALENDAR_API = "https://ac.nowcoder.com/acm/calendar/contest"

    def fetch(self) -> List[Competition]:
        data = http.get_json(
            self.CALENDAR_API,
            headers=self._headers(
                {
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://ac.nowcoder.com/acm/contest/calendar",
                }
            ),
            timeout=self._timeout(),
        )
        out: List[Competition] = []
        for item in data.get("data") or []:
            c = self._convert(item)
            if c is not None:
                out.append(c)
        return out

    def _convert(self, item: dict) -> Optional[Competition]:
        name = (item.get("contestName") or "").strip()
        if not name:
            return None
        oj = (item.get("ojName") or "").strip() or "NowCoder"
        start = _ms_to_dt(item.get("startTime"))
        end = _ms_to_dt(item.get("endTime"))
        # 只保留未开始/进行中的（结束时间在未来）
        if end and _parse(end) < datetime.now():
            return None
        status = "进行中" if start and _parse(start) <= datetime.now() else "未开始"
        return Competition(
            key=f"nowcoder:{oj}:{item.get('contestId') or name}",
            title=name,
            platform=self.platform,
            organizer=oj,
            url=(item.get("link") or "").strip(),
            deadline=end,
            reward="",
            comp_type="算法竞赛",
            status=status,
            enabled_date=start,
        )


def _ms_to_dt(v) -> str:
    """毫秒时间戳 -> 'YYYY-MM-DD HH:MM'（本地时区），便于看清比赛时间段。"""
    try:
        ts = int(v)
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def _parse(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.min
