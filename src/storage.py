# -*- coding: utf-8 -*-
"""增量存储：data/state.json 记录所有见过的比赛，用于识别"新比赛"。"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Tuple

from .models import Competition


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
            except Exception:
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
        self.data["last_run"] = datetime.now().isoformat(timespec="seconds")
        self._save()

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
