# -*- coding: utf-8 -*-
"""飞书群机器人推送。

两种用法，任选其一，都不需要在飞书开放平台发布版本：

1. 自定义机器人 Webhook（推荐，最简单）
   飞书群 -> 设置 -> 群机器人 -> 添加机器人 -> 自定义机器人
   - 创建时若勾选了"签名校验"，把密钥填进 config.json 的 feishu_secret
   - 创建时若勾选了"自定义关键词"，推送文本需包含该关键词
   然后把 Webhook 填进 config.json 的 feishu_webhook。

2. 企业自建应用（需要飞书开放平台开发+发布，不推荐本场景）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from . import http


class FeishuNotifier:
    def __init__(self, webhook: str, secret: str = "", timeout: int = 15):
        self.webhook = (webhook or "").strip()
        self.secret = (secret or "").strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.webhook) and "hook" in self.webhook

    def _payload(self, text: str) -> dict:
        payload = {"msg_type": "text", "content": {"text": text}}
        # 机器人开启了"签名校验"时，需要带 timestamp + sign
        if self.secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{self.secret}"
            hmac_code = hmac.new(
                string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
            ).digest()
            payload["timestamp"] = timestamp
            payload["sign"] = base64.b64encode(hmac_code).decode("utf-8")
        return payload

    def _post(self, payload: dict, retries: int = 2) -> Optional[dict]:
        if not self.enabled:
            return None
        last_err = None
        for i in range(retries + 1):
            try:
                status, raw, _hdrs = http.post(
                    self.webhook,
                    data=json.dumps(payload, ensure_ascii=False),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                resp = json.loads(raw.decode("utf-8", "ignore"))
                if resp.get("code") not in (0, None):
                    raise RuntimeError(f"feishu api error: {resp}")
                return resp
            except Exception as e:  # noqa: BLE001
                last_err = e
                if i < retries:
                    time.sleep(2 * (i + 1))
        raise RuntimeError(f"发送飞书消息失败: {last_err}")

    def send_text(self, text: str, retries: int = 2) -> Optional[dict]:
        """发送纯文本消息。"""
        return self._post(self._payload(text), retries)

    def send_card(self, card: dict, retries: int = 2) -> Optional[dict]:
        """发送交互卡片（含原生表格组件）。"""
        return self._post({"msg_type": "interactive", "card": card}, retries)

    def send_test(self, bot_name: str = "赛探") -> Optional[dict]:
        return self.send_text(
            f"✅ {bot_name}已接通！\n"
            "以后每天扫描到新比赛会自动推送到本群。\n"
            "（这是一条测试消息）"
        )
