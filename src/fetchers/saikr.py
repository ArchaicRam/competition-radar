# -*- coding: utf-8 -*-
"""赛氪（saikr.com）抓取器：学会级赛事聚合广场。

前端是 Vite SPA，但列表接口无需登录（从 bundle 提取，基址见首页注释）：
  GET https://apiv4buffer.saikr.com/api/pc/contest/lists
      ?page=1&limit=20&class_id=2|6|34|1006|5|4|1
返回 {code:200, data:{list:[...], total}}。行字段：
  contest_id/contest_name/contest_url(相对路径)/organiser(主办单位)/
  regist_start_time/regist_end_time/contest_start_time/contest_end_time(unix)/
  time_name(正在报名/比赛进行中/比赛结束)/level_name/contest_class_second

class_id 只取计算机相关 7 类（数学建模/程序设计/机器人/电子自动化/
计算机&信息技术/大数据/人工智能）；站内仍混有"答题领证书"类低质赛，
跑题/低质过滤交给 runner 的 is_off_topic / is_low_value 统一处理。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import List, Optional

from .. import http
from ..models import Competition
from .base import BaseFetcher

API = "https://apiv4buffer.saikr.com/api/pc/contest/lists"
PAGE_BASE = "https://www.saikr.com/"
# 数学建模/程序设计/机器人/电子&自动化/计算机&信息技术/大数据/人工智能
CLASS_IDS = "1|2|4|5|6|34|1006"

# contest_class_second → 本项目的赛道类型
_TYPE_MAP = {
    "ai": "AI",
    "big_data": "数据",
    "computer": "开发",
    "mcm": "数学建模",
    "match": "数学建模",
}
_STATUS_MAP = {"正在报名": "报名中", "比赛进行中": "进行中", "比赛结束": "已结束"}

_PROMO_PREFIX = re.compile(r"^(?:【[^】]*】\s*)+")


class SaikrFetcher(BaseFetcher):
    platform = "saikr"

    def fetch(self, pages: int = 3, limit: int = 20) -> List[Competition]:
        out: List[Competition] = []
        seen = set()
        for page in range(1, pages + 1):
            url = f"{API}?page={page}&limit={limit}&class_id={CLASS_IDS}"
            status, raw, _hdrs = http.get(
                url,
                headers=self._headers({"Accept": "application/json",
                                       "Referer": "https://www.saikr.com/"}),
                timeout=self._timeout(),
            )
            if status != 200:
                raise RuntimeError(f"赛氪列表接口返回 HTTP {status}")
            data = json.loads(raw.decode("utf-8", "ignore"))
            rows = (data.get("data") or {}).get("list") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise RuntimeError(f"赛氪列表接口响应结构异常: {type(data).__name__}")
            for row in rows:
                c = self._convert(row)
                if c is not None and c.key not in seen:
                    seen.add(c.key)
                    out.append(c)
            if len(rows) < limit:
                break  # 最后一页
        return out

    def _convert(self, row: dict) -> Optional[Competition]:
        cid = str(row.get("contest_id") or "").strip()
        title = _PROMO_PREFIX.sub("", str(row.get("contest_name") or "")).strip()
        if not cid or not title:
            return None
        regist_end = _ts_to_date(row.get("regist_end_time"))
        contest_end = _ts_to_date(row.get("contest_end_time"))
        contest_start = _ts_to_date(row.get("contest_start_time"))
        if not regist_end and not contest_end:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        regist_start = _ts_to_date(row.get("regist_start_time"))
        # 截止优先取报名截止；报名已截止但比赛未结束的，取比赛结束。
        # enabled_date 必须与 deadline 同轴（报名截止↔报名开始，
        # 比赛结束↔比赛开始）——比赛开始普遍晚于报名截止，混轴会被
        # runner 的"开始晚于截止"校验误杀。
        if regist_end and regist_end >= today:
            deadline = regist_end
            enabled = regist_start
        elif contest_end and contest_end >= today:
            deadline = contest_end
            enabled = contest_start
        else:
            deadline = contest_end or regist_end
            enabled = contest_start or regist_start
        status = _STATUS_MAP.get(str(row.get("time_name") or "").strip(), "")
        if not status:
            if deadline and deadline >= today:
                status = "进行中" if (enabled and enabled <= today) else "报名中"
            else:
                status = "已结束"
        rel = str(row.get("contest_url") or "").strip().lstrip("/")
        return Competition(
            key=f"saikr:{cid}",
            title=title,
            platform=self.platform,
            organizer=str(row.get("organiser") or "").strip(),
            url=PAGE_BASE + rel if rel else PAGE_BASE,
            deadline=deadline,
            comp_type=_TYPE_MAP.get(str(row.get("contest_class_second") or ""), "综合"),
            status=status,
            enabled_date=enabled,
        )


def _ts_to_date(v) -> str:
    """unix 秒级时间戳（可能是 int/float/数字字符串）→ YYYY-MM-DD。"""
    try:
        ts = int(float(str(v).strip()))
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
