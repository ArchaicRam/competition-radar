# -*- coding: utf-8 -*-
"""推送消息模板"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .models import Competition


def _days_left(deadline: str) -> Optional[int]:
    """解析截止日期，返回距离今天的天数；解析失败或已过期返回 None。"""
    s = (deadline or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return None
    delta = (d - datetime.now(d.tzinfo)).days if d.tzinfo else (d - datetime.now()).days
    return delta


def build_message(
    new: List[Competition],
    updated: List[Competition],
    max_items: int = 20,
    deadline_alert_days: int = 14,
    bot_name: str = "竞赛雷达",
) -> str:
    """拼接新比赛 + 更新比赛的推送文案。"""
    if not new and not updated:
        return ""
    head = f"📡 【{bot_name}】新发现 {len(new)} 场比赛"
    if updated:
        head += f" ｜ {len(updated)} 场信息有更新"
    lines = [head, ""]
    for i, c in enumerate(new[:max_items], 1):
        flag = ""
        d = _days_left(c.deadline)
        if d is not None and 0 <= d <= deadline_alert_days:
            flag = f" ⏰{d}天后截止" if d > 0 else " ⏰今天截止"
        lines.append(
            f"{i}. 🏆 {c.title}{flag}\n"
            f"    主办 {c.organizer or '—'}｜类型 {c.comp_type or '—'}\n"
            f"    截止 {c.deadline or '未知'}｜奖金 {c.reward or '—'}\n"
            f"    🔗 {c.url}"
        )
    if len(new) > max_items:
        lines.append(f"\n… 另有 {len(new) - max_items} 场新比赛，详见状态文件/CSV 台账。")
    if updated:
        lines.append("")
        lines.append(f"🔄 有更新的比赛（前 {min(5, len(updated))} 场）：")
        for c in updated[:5]:
            lines.append(f"- {c.title}（截止 {c.deadline or '未知'}｜{c.status or ''}）")
    return "\n".join(lines)


def build_no_new_message(bot_name: str = "竞赛雷达") -> str:
    return f"😴 【{bot_name}】今日扫描完毕，没有发现新比赛。"
