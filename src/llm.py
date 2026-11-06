# -*- coding: utf-8 -*-
"""LLM 客户端：OpenAI 兼容 Chat Completions（默认 DeepSeek 官方 API）。

配置（config.json）：
  llm_api_key    必填，DeepSeek 开放平台 API Key（platform.deepseek.com）
  llm_base_url   默认 https://api.deepseek.com（官方地址；不要带 /v1，本模块自己拼 /chat/completions）
  llm_model      默认 deepseek-flash（官方现有：deepseek-flash / deepseek-v4-pro）

注意：老配置里若是智谱的 https://open.bigmodel.cn/api/coding/paas/v4 + glm-5.3-flash，
换成 DeepSeek 官方时必须同时改 base_url 和 model，只改 key 会 404。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from . import http


class LLMError(RuntimeError):
    pass


def chat(
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
    timeout: int = 180,
) -> str:
    api_key = (cfg.get("llm_api_key") or "").strip()
    if not api_key:
        raise LLMError("未配置 llm_api_key")
    base = (cfg.get("llm_base_url") or "https://api.deepseek.com").rstrip("/")
    model = cfg.get("llm_model") or "deepseek-flash"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens or int(cfg.get("llm_max_tokens", 1200)),
        "temperature": temperature,
        "stream": False,
    }
    url = f"{base}/chat/completions"
    status, raw, _hdrs = http.post(
        url,
        data=json.dumps(payload, ensure_ascii=False),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        timeout=timeout,
        retries=1,  # LLM 接口偶发 5xx/超时很常见，幂等推理请求可安全重试
    )
    if status != 200:
        raise LLMError(f"LLM 接口错误 {status}: {raw.decode('utf-8', 'ignore')[:300]}")
    data = json.loads(raw.decode("utf-8", "ignore"))
    try:
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"LLM 响应结构异常: {e}") from e

    if not content:
        # deepseek-flash 是**推理模型**：先产 reasoning_content 再产 content，
        # max_tokens 太小会把额度全耗在思维链上，content 变成空串
        # （finish_reason=length）。这时要给出能直接定位的报错，而不是空字符串。
        reason = choice.get("finish_reason")
        thinking = (msg.get("reasoning_content") or "")
        if reason == "length":
            raise LLMError(
                "LLM 输出被 max_tokens 截断：content 为空"
                f"（模型 {model} 为推理模型，思维链已消耗额度，请调大 llm_max_tokens，"
                f"当前 {payload['max_tokens']}；思维链长度 {len(thinking)} 字）"
            )
        raise LLMError(f"LLM 返回空内容（finish_reason={reason}，模型 {model}）")
    return content


def chat_json(
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
    max_tokens: Optional[int] = None,
) -> Any:
    """要求 LLM 返回 JSON，带容错解析（去掉代码围栏/杂音）。"""
    text = chat(messages, cfg, max_tokens=max_tokens, temperature=0.1)
    return parse_json(text)


def parse_json(text: str) -> Any:
    text = text.strip()
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取第一个 { ... } 或 [ ... ] 完整片段
        for open_c, close_c in (("{", "}"), ("[", "]")):
            s = text.find(open_c)
            if s == -1:
                continue
            depth = 0
            for i in range(s, len(text)):
                if text[i] == open_c:
                    depth += 1
                elif text[i] == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[s : i + 1])
                        except json.JSONDecodeError:
                            break
        raise LLMError(f"LLM 输出不是合法 JSON: {text[:300]}")
