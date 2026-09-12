# -*- coding: utf-8 -*-
"""增量存储：data/state.json 记录所有见过的比赛，用于识别"新比赛"。"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from .models import Competition

log = logging.getLogger("storage")

# 已截止超过该天数的条目会被清理，防止 state.json / 台账无限增长
PRUNE_AFTER_DAYS = 90


class Store:
    def __init__(self, path: str):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "competitions" in data:
                    return data
                log.warning("state.json 格式异常（缺少 competitions 字段），已备份并重建空状态")
            except Exception as e:  # noqa: BLE001
                log.warning("state.json 读取失败（%s），已备份并重建空状态", e)
            # 备份损坏文件，避免直接覆盖丢失现场；下次运行会重新发现所有比赛
            try:
                shutil.copy2(self.path, self.path + ".bak")
            except OSError:
                pass
        return {"version": 1, "competitions": {}, "last_run": None}

    def known(self) -> Dict[str, dict]:
        return self.data["competitions"]

    def diff(self, fetched: List[Competition]) -> Tuple[List[Competition], List[Competition]]:
        """返回 (新比赛, 信息有更新的比赛)。"""
        known = self.known()
        new: List[Competition] = []
        updated: List[Competition] = []
        for c in fetched:
            old = known.get(c.key)
            if old is None:
                new.append(c)
            else:
                if (
                    old.get("deadline") != c.deadline
                    or old.get("status") != c.status
                    or old.get("reward") != c.reward
                    or old.get("title") != c.title
                    or old.get("url") != c.url
                ):
                    updated.append(c)
        return new, updated

    def update(self, fetched: List[Competition]) -> None:
        known = self.known()
        for c in fetched:
            d = c.to_dict()
            old = known.get(c.key)
            # 保留"首次发现时间"：detected_at 是入表时间，不能随每次抓取被刷新
            if old and old.get("detected_at"):
                d["detected_at"] = old["detected_at"]
            known[c.key] = d
        self._prune()
        self.data["last_run"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def _prune(self) -> int:
        """清理过期条目，防止状态无限膨胀。

        - 有截止日期：截止超过 PRUNE_AFTER_DAYS 天即清理
        - 无截止日期（AI 发现的线索常见）：入表超过 PRUNE_AFTER_DAYS 天仍无进展也清理
        """
        cutoff = (datetime.now() - timedelta(days=PRUNE_AFTER_DAYS)).strftime("%Y-%m-%d")
        stale = []
        for key, d in self.known().items():
            dl = (d.get("deadline") or "").strip()[:10]
            if dl:
                if dl < cutoff:
                    stale.append(key)
                continue
            det = (d.get("detected_at") or "").strip()[:10]
            if det and det < cutoff:
                stale.append(key)
        for key in stale:
            del self.known()[key]
        if stale:
            log.info("清理了 %d 条过期状态（超过 %d 天）", len(stale), PRUNE_AFTER_DAYS)
        return len(stale)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def reset(self) -> None:
        self.data = {"version": 1, "competitions": {}, "last_run": None}
        self._save()

    def all_sorted(self) -> List[dict]:
        """全部已知比赛，按截止日期排序（无截止日期的放最后）。"""
        items = list(self.known().values())

        def sort_key(d: dict):
            dl = (d.get("deadline") or "").strip()
            return (0, dl) if dl else (1, "")

        items.sort(key=sort_key)
        return items
