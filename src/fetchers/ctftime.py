# -*- coding: utf-8 -*-
"""CTFtime（ctftime.org）抓取器：全球 CTF 赛事日历。

官方公开 JSON API（无需认证）：
  GET https://ctftime.org/api/v1/events/?start=<unix>&finish=<unix>&limit=30
返回未来一段窗口内登记的 CTF 赛事数组（含国内强网杯/XCTF 分站赛等，
只要主办方在 CTFtime 登记就能看到），字段：
  {id, title, start, finish, organizers:[{name}], url(官网), ctftime_url,
   format(Jeopardy/Attack-Defense), prizes, restrictions, ...}

说明：deadline 用赛事 finish 日期（与天池 raceEndTime 同口径）；
已结束的赛事由 runner 的数据质量校验统一过滤。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from .. import http
from ..models import Competition
from .base import BaseFetcher


class CtfTimeFetcher(BaseFetcher):
    platform = "ctftime"
    PAGE = "https://ctftime.org/events"
    API = "https://ctftime.org/api/v1/events/"

    def fetch(self, days_ahead: int = 60, limit: int = 30) -> List[Competition]:
        now = datetime.now()
        url = (
            f"{self.API}?start={int(now.timestamp())}"
            f"&finish={int((now + timedelta(days=days_ahead)).timestamp())}"
            f"&limit={limit}"
        )
        status, raw, _hdrs = http.get(
            url,
            headers={"Referer": self.PAGE, "Accept": "application/json"},
            timeout=self._timeout(),
        )
        if status != 200:
            raise RuntimeError(f"CTFtime API 返回 HTTP {status}")
        import json

        events = json.loads(raw.decode("utf-8", "ignore"))
        if not isinstance(events, list):
            raise RuntimeError(f"CTFtime API 响应结构异常: {type(events).__name__}")
        out = []
        for ev in events:
            c = self._convert(ev)
            if c is not None:
                out.append(c)
        return out

    def _convert(self, ev: dict) -> Optional[Competition]:
        title = str(ev.get("title") or "").strip()
        ev_id = ev.get("id") or ev.get("ctf_id")
        if not title or ev_id is None:
            return None
        finish = _fmt_date(ev.get("finish"))
        start = _fmt_date(ev.get("start"))
        if not finish:
            return None
        if ev.get("onsite") and not (ev.get("location") or ""):
            pass  # 现场赛照常收录，location 缺失不拦截
        organizers = ", ".join(
            str(o.get("name") or "").strip()
            for o in (ev.get("organizers") or [])
            if isinstance(o, dict) and o.get("name")
        )
        link = (ev.get("url") or "").strip() or (ev.get("ctftime_url") or "").strip()
        fmt = str(ev.get("format") or "").strip()
        prizes = str(ev.get("prizes") or "").strip()
        # "TBA"/空奖品不展示；超长截断
        if prizes and prizes.upper() != "TBA":
            prizes = prizes[:60]
        else:
            prizes = ""
        comp_type = "网络安全"
        if fmt and fmt.upper() == "ATTACK-DEFENSE":
            comp_type = "网络安全·攻防"
        return Competition(
            key=f"ctftime:{ev_id}",
            title=title,
            platform=self.platform,
            organizer=organizers,
            url=link,
            deadline=finish,
            reward=prizes,
            comp_type=comp_type,
            status=_status(start, finish),
            enabled_date=start,
        )


def _fmt_date(v) -> str:
    """ISO 时间戳（2026-09-17T05:00:00+00:00）→ 日期字符串。"""
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 else ""


def _status(start: str, finish: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    if start and start <= now:
        return "进行中"
    return "未开始"
