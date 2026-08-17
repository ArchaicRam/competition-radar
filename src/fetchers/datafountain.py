# -*- coding: utf-8 -*-
"""DataFountain（datafountain.cn）抓取器。

官方 API（已实测可用）：
  GET https://www.datafountain.cn/api/competitions?type=0&status=0&page=1&per_page=20
返回 JSON，数据在 cmpt.competitions 数组里。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .. import http
from ..models import Competition
from .base import BaseFetcher

_STATE_CN = {
    "NOT_START": "未开始",
    "IN_SERVICE": "进行中",
    "ENDED": "已结束",
    "FINISHED": "已结束",
    "OUT_SERVICE": "已结束",
}


class DataFountainFetcher(BaseFetcher):
    platform = "datafountain"
    LIST_API = "https://www.datafountain.cn/api/competitions"

    def fetch(self, max_pages: int = 3, per_page: int = 20) -> List[Competition]:
        out: List[Competition] = []
        for page in range(1, max_pages + 1):
            url = f"{self.LIST_API}?type=0&status=0&page={page}&per_page={per_page}"
            data = http.get_json(
                url,
                headers=self._headers({"Referer": "https://www.datafountain.cn/"}),
                timeout=self._timeout(),
            )
            comps = (data.get("cmpt") or {}).get("competitions") or []
            if not comps:
                break
            for c in comps:
                if not c.get("isPublished"):
                    continue
                comp = self._convert(c)
                if comp is not None:
                    out.append(comp)
        return out

    def _convert(self, c: dict) -> Optional[Competition]:
        # 已结束的赛事不推（状态或截止时间任一判断）
        state = c.get("state")
        if state in ("OUT_SERVICE", "ENDED", "FINISHED"):
            return None
        end_time = _norm_date(c.get("endTime"))
        if end_time and _is_past(end_time):
            return None
        cid = c.get("id")
        title = (c.get("title") or "").strip()
        orgs = [o.get("name", "").strip() for o in (c.get("organizers") or [])]
        organizer = "、".join([o for o in orgs if o])
        tags = [t.get("nameCn", "").strip() for t in (c.get("tags") or [])]
        comp_type = (c.get("typeLabel") or tags[0] if tags else "") or ""
        reward = c.get("reward")
        reward_str = ""
        if reward not in (None, ""):
            try:
                reward_str = f"¥{int(reward):,}"
            except (TypeError, ValueError):
                reward_str = str(reward)
        status = _STATE_CN.get(state, str(state or ""))
        if c.get("isOpenSignup") and status in ("进行中", "未开始", ""):
            status = "报名中"
        return Competition(
            key=f"datafountain:{cid}",
            title=title,
            platform=self.platform,
            organizer=organizer,
            url=f"https://www.datafountain.cn/competitions/{cid}",
            deadline=end_time,
            reward=reward_str,
            comp_type=comp_type,
            status=status,
            enabled_date=_norm_date(c.get("startTime")),
        )


def _is_past(date_str: str) -> bool:
    if not date_str:
        return False
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") < datetime.now()
    except ValueError:
        return False


def _norm_date(iso: str | None) -> str:
    """ISO 时间 -> YYYY-MM-DD，解析失败原样返回。"""
    if not iso:
        return ""
    try:
        from datetime import datetime

        s = iso
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso
