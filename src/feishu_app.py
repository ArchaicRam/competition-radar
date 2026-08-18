# -*- coding: utf-8 -*-
"""应用机器人发消息（走 lark-cli，可进任意群，换群无需重建机器人）。

配置：config.json 的 feishu_chat_id 填目标群 chat_id（oc_xxx），
再配 lark_profile（默认 jingsai）即可。配了之后优先用应用机器人，
webhook 作为自动降级通道。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from . import lark as lark_mod


def send_card(chat_id: str, card: Dict, profile: str = "jingsai") -> Dict[str, Any]:
    """发送交互卡片。"""
    content = json.dumps(card, ensure_ascii=False)
    return lark_mod.lark(
        ["--profile", profile, "im", "+messages-send",
         "--chat-id", chat_id, "--msg-type", "interactive", "--content", content]
    )


def send_text(chat_id: str, text: str, profile: str = "jingsai") -> Dict[str, Any]:
    """发送纯文本。"""
    return lark_mod.lark(
        ["--profile", profile, "im", "+messages-send",
         "--chat-id", chat_id, "--text", text]
    )
