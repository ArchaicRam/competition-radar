# -*- coding: utf-8 -*-
"""全国人工智能应用创新大赛（ai-race.com.cn）抓取器。

官网是 Vite SPA，但后端有无需登录的开放接口（从前端 bundle 提取）：
  GET https://www.ai-race.com.cn/prod-api/open/competition
返回大赛数组，每场含 trackList[].stageList[]（校赛/区域赛/全国赛，
同一阶段因分赛区/分场景会重复多条，各带起止日期）。
主办方为中国技术经济学会（中国科协主管的全国性学会）——赛事不在
高教学会目录，但规模大（首届 632 所高校），属"目录外正规赛"。

口径：
  deadline 取今天之后最近的阶段结束日期（进行中取当前阶段结束）；
  全部阶段已结束的照常返回（status=已结束），由 runner 的数据质量
  校验统一过滤。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Tuple

from .. import http
from ..models import Competition
from .base import BaseFetcher

ORGANIZER = "中国技术经济学会"


class AiRaceFetcher(BaseFetcher):
    platform = "ai_race"
    PAGE = "https://www.ai-race.com.cn/"
    API = "https://www.ai-race.com.cn/prod-api/open/competition"

    def fetch(self) -> List[Competition]:
        status, raw, _hdrs = http.get(
            self.API,
            headers=self._headers({"Accept": "application/json"}),
            timeout=self._timeout(),
        )
        if status != 200:
            raise RuntimeError(f"ai-race API 返回 HTTP {status}")
        data = json.loads(raw.decode("utf-8", "ignore"))
        comps = data.get("data") if isinstance(data, dict) else None
        if not isinstance(comps, list):
            raise RuntimeError(f"ai-race API 响应结构异常: {type(data).__name__}")
        out = []
        for c in comps:
            conv = self._convert(c)
            if conv is not None:
                out.append(conv)
        return out

    def _convert(self, comp: dict) -> Optional[Competition]:
        title = str(comp.get("competitionName") or "").strip()
        comp_id = str(comp.get("id") or "").strip()
        if not title or not comp_id:
            return None
        stages: List[Tuple[str, str]] = []
        for track in comp.get("trackList") or []:
            for st in track.get("stageList") or []:
                start = str(st.get("startDt") or "").strip()[:10]
                end = str(st.get("endDt") or "").strip()[:10]
                if end:
                    stages.append((start, end))
        if not stages:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        upcoming = [s for s in stages if s[1] >= today]
        if upcoming:
            deadline = min(s[1] for s in upcoming)
            started = [s[0] for s in upcoming if s[0] and s[0] <= today]
            starts = [s[0] for s in upcoming if s[0]]
            # 已开始的阶段存在 → 进行中；否则等未来阶段开赛 → 报名中
            stat = "进行中" if started else "报名中"
            start = min(started) if started else (min(starts) if starts else "")
        else:
            deadline = max(s[1] for s in stages)
            starts = [s[0] for s in stages if s[0]]
            start = min(starts) if starts else ""
            stat = "已结束"
        return Competition(
            key=f"ai_race:{comp_id}",
            title=title,
            platform=self.platform,
            organizer=ORGANIZER,
            url=self.PAGE,
            deadline=deadline,
            comp_type="AI",
            status=stat,
            enabled_date=start,
        )
