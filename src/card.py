# -*- coding: utf-8 -*-
"""飞书"情报日报"卡片构建。

卡片只放精炼摘要（今日新增 / 即将截止 / 数据来源），
完整明细见 Excel 台账（每日生成，卡片里给链接/路径）。
"""
from __future__ import annotations

from typing import Dict, List, Set

from .message import _days_left
from .official import is_official
from .platforms import SOURCE_INFO


def build_digest_card(
    competitions: List,
    new_keys: Set[str],
    bot_name: str = "竞赛雷达",
    deadline_alert_days: int = 14,
    excel_link: str = "",
    excel_path: str = "",
    ai_digest_text: str = "",
    site_link: str = "",
    max_list: int = 10,
) -> Dict:
    """构建情报日报卡片。"""
    comps = competitions
    new_comps = [c for c in comps if c.key in new_keys]
    official_count = sum(1 for c in comps if is_official(c.title, c.organizer))
    upcoming = [
        c for c in comps
        if (d := _days_left(c.deadline)) is not None and 0 <= d <= deadline_alert_days
    ]
    upcoming.sort(key=lambda c: c.deadline)

    elements: List[Dict] = []
    summary = f"共 **{len(comps)}** 场进行中 ｜ 官方赛事 **{official_count}** 场"
    if new_comps:
        summary += f" ｜ 今日新增 **{len(new_comps)}** 场"
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": summary}})

    if new_comps:
        lines = []
        for c in new_comps[:max_list]:
            deadline_info = c.deadline or c.status or "截止未知"
            lines.append(f"🆕 **<font color='red'>[{_esc(c.title)}]({c.url})</font>**（{deadline_info}）")
        if len(new_comps) > max_list:
            lines.append(f"… 另有 {len(new_comps) - max_list} 场见 Excel 台账")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": "**今日新增：**\n" + "\n".join(lines)}}
        )

    if ai_digest_text:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"✨ **AI 今日看点**\n{ai_digest_text}"}}
        )

    if upcoming:
        lines = []
        for c in upcoming[:max_list]:
            d = _days_left(c.deadline)
            mark = f"⏰{d}天后" if d > 0 else "⏰今天"
            lines.append(f"**[{_esc(c.title)}]({c.url})** {mark}｜{c.deadline}｜{c.status or ''}")
        if len(upcoming) > max_list:
            lines.append(f"… 另有 {len(upcoming) - max_list} 场见 Excel 台账")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**⏰ {deadline_alert_days}天内即将截止：**\n" + "\n".join(lines)}}
        )

    # 数据来源
    src_text = "**数据来源：**\n" + "\n".join(
        f"- {name}：{url}" for name, url in SOURCE_INFO.values()
    )
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": src_text}})

    # 卡片底部链接区：网页版总览 / 在线表格 / Excel 路径
    links = []
    if site_link:
        links.append(f"**[🌐 网页版总览]({site_link})**")
    if excel_link:
        label = "📊 查看在线表格" if "/sheets/" in excel_link else "📊 下载 Excel 台账"
        links.append(f"**[{label}]({excel_link})**")
    if links:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": " ｜ ".join(links) + "（每日更新，红底=今日新增）",
                },
            }
        )
    elif excel_path:
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"📊 Excel 台账：{excel_path}（本机路径，群内不可点；配置 excel_link 后此处显示可点链接）",
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red" if new_comps else "blue",
            "title": {
                "tag": "plain_text",
                "content": f"📡 {bot_name} · 情报日报" + (f"（今日新增 {len(new_comps)}）" if new_comps else ""),
            },
        },
        "elements": elements,
    }


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("|", "｜")
        .replace("\n", " ")
        .replace("<", "＜")
        .replace(">", "＞")
        .replace("**", "＊＊")
        # markdown 链接文本里的括号/反斜杠会破坏 [text](url) 结构
        .replace("\\", "＼")
        .replace("(", "（")
        .replace(")", "）")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\ufeff", "")
    )
