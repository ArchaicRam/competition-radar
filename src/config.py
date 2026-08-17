# -*- coding: utf-8 -*-
"""配置加载：config.json 优先，其次环境变量，最后内置默认值。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "feishu_webhook": "",
    "feishu_secret": "",
    "bot_name": "竞赛雷达",
    "sources": ["tianchi", "datafountain", "nowcoder", "xfyun", "kaggle"],
    "only_new": True,
    "digest_when_no_new": False,
    "send_table_daily": True,
    "max_table_rows": 0,
    "excel_file": "data/competitions.xlsx",
    "excel_link": "",
    "feishu_sheet_url": "",
    "lark_profile": "jingsai",
    "official_keywords": [],
    "llm_api_key": "",
    "llm_base_url": "https://api.deepseek.com",
    "llm_model": "deepseek-chat",
    "llm_max_tokens": 1200,
    "ai_discover": True,
    "ai_digest": True,
    "seed_sources": [
        {"name": "中国软件杯", "url": "https://www.cnsoftbei.com/"},
        {"name": "我爱竞赛网", "url": "https://www.52jingsai.com/"},
    ],
    "max_items_per_push": 20,
    "deadline_alert_days": 14,
    "data_file": "data/state.json",
    "http_timeout": 30,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

_ENV_MAP = {
    "FEISHU_WEBHOOK": "feishu_webhook",
    "FEISHU_SECRET": "feishu_secret",
    "SOURCES": "sources",
    "DATA_FILE": "data_file",
    "HTTP_TIMEOUT": "http_timeout",
    "KAGGLE_USERNAME": "kaggle_username",
    "KAGGLE_KEY": "kaggle_key",
    "LLM_API_KEY": "llm_api_key",
}


def load_config(path: str = "config.json") -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    # 环境变量覆盖（方便 GitHub Actions / CI 免配置文件）
    for env, key in _ENV_MAP.items():
        val = os.environ.get(env)
        if val is None:
            continue
        if key == "sources":
            cfg[key] = [s.strip() for s in val.split(",") if s.strip()]
        elif key == "http_timeout":
            cfg[key] = int(val)
        else:
            cfg[key] = val
    return cfg


def normalize_sources(sources: List[str]) -> List[str]:
    known = {"tianchi", "datafountain", "nowcoder", "xfyun", "kaggle", "saikr"}
    out = []
    for s in sources:
        s = (s or "").strip().lower()
        if s in known:
            out.append(s)
    return out
