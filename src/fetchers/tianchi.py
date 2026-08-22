# -*- coding: utf-8 -*-
"""阿里云天池（tianchi.aliyun.com）抓取器。

天池列表页是低代码 SPA，数据接口（已从 JS bundle 挖出并实测可用）：
  GET https://tianchi.aliyun.com/v3/proxy/competition/api/race/page?pageNum=1&pageSize=50
  需要先访问页面拿 cookie（_csrf），再带 X-CSRF-Token 头。
返回 {"data":{"list":[{raceId,name,signupStartTime,signupEndTime,raceEndTime,bonus,...}]}}。

注意：天池有反爬，数据中心 IP 可能 403；被拦截时抛 FetcherSkip（记日志、不算失败）。
"""
from __future__ import annotations

import json
import urllib.request as _urllib
from datetime import datetime
from typing import List, Optional

import http.cookiejar as _cookiejar

from .. import http
from ..models import Competition
from .base import BaseFetcher, FetcherSkip


class TianchiFetcher(BaseFetcher):
    platform = "tianchi"
    PAGE = "https://tianchi.aliyun.com/competition/programmingList"
    API = "https://tianchi.aliyun.com/v3/proxy/competition/api/race/page"

    def fetch(self, max_pages: int = 2, page_size: int = 50) -> List[Competition]:
        try:
            payloads = self._call_api(max_pages, page_size)
        except Exception as e:  # noqa: BLE001
            # 只有明确的反爬/风控信号才按 FetcherSkip 处理（记日志、不算失败）；
            # 其余异常（代码 bug、DNS、JSON 解析等）原样抛出，进入 result["errors"]
            msg = str(e).lower()
            if "403" in msg or "forbidden" in msg or "csrf" in msg or "captcha" in msg:
                raise FetcherSkip(f"天池接口被反爬拦截（{e}），本次跳过；可手动查看 {self.PAGE}") from e
            raise
        out: List[Competition] = []
        for payload in payloads:
            for rec in (payload.get("data") or {}).get("list") or []:
                c = self._convert(rec)
                if c is not None:
                    out.append(c)
        return out

    def _call_api(self, max_pages: int, page_size: int) -> List[dict]:
        cj = _cookiejar.CookieJar()
        opener = _urllib.build_opener(_urllib.HTTPCookieProcessor(cj))
        opener.addheaders = [
            ("User-Agent", self.cfg.get("user_agent", http.DEFAULT_UA)),
            ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
        ]
        opener.open(_urllib.Request(self.PAGE), timeout=self._timeout()).read()
        csrf = next((c.value for c in cj if c.name.lower() == "_csrf"), "")
        payloads = []
        for page in range(1, max_pages + 1):
            url = f"{self.API}?pageNum={page}&pageSize={page_size}"
            req = _urllib.Request(
                url,
                headers={
                    "Origin": "https://tianchi.aliyun.com",
                    "Referer": self.PAGE,
                    "Accept": "application/json, text/plain, */*",
                    "X-CSRF-Token": csrf,
                },
                method="GET",
            )
            with opener.open(req, timeout=self._timeout()) as r:
                raw = r.read()
            payload = json.loads(raw.decode("utf-8", "ignore"))
            payloads.append(payload)
            if not (payload.get("data") or {}).get("hasNextPage"):
                break
        return payloads

    def _convert(self, r: dict) -> Optional[Competition]:
        title = str(r.get("name") or "").strip()
        if not title:
            return None
        race_id = r.get("raceId")
        bonus = r.get("bonus")
        reward = f"¥{int(bonus):,}" if isinstance(bonus, (int, float)) and bonus else ""
        tags = [t.get("tagNameCn") or t.get("tagName") for t in (r.get("tagsList") or [])]
        comp_type = "、".join([t for t in tags if t]) or ""
        deadline = _fmt_date(r.get("signupEndTime")) or _fmt_date(r.get("raceEndTime"))
        status = _status(r.get("signupStartTime"), r.get("signupEndTime"), r.get("raceEndTime"))
        if status == "已结束":
            return None
        return Competition(
            key=f"tianchi:{race_id or title}",
            title=title,
            platform=self.platform,
            organizer=str(r.get("organizerName") or r.get("sponsorName") or "").strip(),
            url=f"https://tianchi.aliyun.com/competition/entrance/{race_id}" if race_id else self.PAGE,
            deadline=deadline,
            reward=reward,
            comp_type=comp_type,
            status=status,
            enabled_date=_fmt_date(r.get("signupStartTime")),
        )


def _fmt_date(v) -> str:
    s = str(v or "").strip()
    if not s or s.lower() == "null":
        return ""
    return s[:10]


def _status(start: str, end: str, race_end: str) -> str:
    now = datetime.now()

    def parse(s):
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            return None

    d_end = parse(end)
    d_race = parse(race_end)
    if d_end and d_end >= now:
        return "报名中"
    if d_race and d_race >= now:
        return "进行中"
    if d_end or d_race:
        return "已结束"  # 有明确时间且都已过去
    return "报名中"  # 时间未知，当作可报名
