# -*- coding: utf-8 -*-
"""AI 日报解读：把当日新增比赛写成"今日看点"。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from . import llm

log = logging.getLogger("ai_digest")


def digest(new_comps: List, cfg: Dict[str, Any]) -> str:
    """生成当日看点文案（<=130 字），失败或未配置时返回空串。"""
    api_key = (cfg.get("llm_api_key") or "").strip()
    if not api_key or not new_comps:
        return ""
    lines = [
        f"- {c.title}｜主办 {c.organizer or '未知'}｜截止 {c.deadline or '未知'}｜{c.comp_type or ''}"
        for c in new_comps[:40]
    ]
    prompt = (
        "以下是今天新出现的比赛/需求征集列表：\n"
        + "\n".join(lines)
        + "\n\n请用不超过130字写一段「今日看点」：突出最值得关注的1-2个活动、"
        "整体类型分布、给大学生社团的建议。只输出正文，不要标题。"
    )
    try:
        return llm.chat(
            [
                {"role": "system", "content": "你是高校竞赛社团的情报顾问，文风简洁、有信息量。"},
                {"role": "user", "content": prompt},
            ],
            cfg,
            max_tokens=300,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("AI 日报解读失败: %s", e)
        return ""
