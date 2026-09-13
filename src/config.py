# -*- coding: utf-8 -*-
"""配置加载：config.json 优先，其次环境变量，最后内置默认值。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "feishu_webhook": "",
    "feishu_secret": "",
    "feishu_chat_id": "",
    "bot_name": "竞赛雷达",
    "sources": ["tianchi", "datafountain", "nowcoder", "xfyun", "kaggle", "ctftime"],
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
        # 教育部/高教学会目录内的官方赛事官网（权威、优先）
        {"name": "中国国际大学生创新大赛", "url": "https://cy.ncss.cn/"},
        {"name": "挑战杯", "url": "http://www.tiaozhanbei.net/"},
        {"name": "中国大学生计算机设计大赛", "url": "http://jsjds.blcu.edu.cn/"},
        {"name": "中国高校计算机大赛", "url": "http://www.c4best.cn/"},
        {"name": "蓝桥杯", "url": "https://dasai.lanqiao.cn/"},
        {"name": "服务外包创新创业大赛", "url": "http://www.fwwb.org.cn/"},
        {"name": "全国大学生信息安全竞赛", "url": "http://www.ciscn.cn/"},
        {"name": "计算机系统能力大赛", "url": "https://compiler.educg.net/"},
        {"name": "研究生创新实践系列大赛", "url": "https://cpipc.acge.org.cn/"},
        {"name": "CCF中国计算机学会", "url": "https://www.ccf.org.cn/"},
        {"name": "百度之星", "url": "https://star.baidu.com/"},
        {"name": "开源之夏", "url": "https://summer-ospp.ac.cn/"},
        # 网络安全专项（官方赛官网 / 安全资讯站 / 众测委托平台）
        {"name": "长城杯铁人三项", "url": "https://ccb.itsec.gov.cn/"},
        {"name": "网鼎杯", "url": "https://wangdingcup.com/"},
        {"name": "XCTF联赛", "url": "http://www.xctf.org.cn/"},
        {"name": "看雪安全社区", "url": "https://www.kanxue.com/"},
        {"name": "FreeBuf", "url": "https://www.freebuf.com/"},
        {"name": "安全客", "url": "https://www.anquanke.com/"},
        {"name": "数据安全职业技能竞赛", "url": "https://js.afdata.org.cn/"},
        {"name": "数字中国创新大赛", "url": "https://www.szzg.gov.cn/"},
        {"name": "补天漏洞响应平台", "url": "https://www.butian.net/"},
        {"name": "漏洞盒子", "url": "https://www.vulbox.com/"},
        # 聚合站 / 企业赛 / 高校教务处（可按需增删）
        {"name": "中国软件杯", "url": "https://www.cnsoftbei.com/"},
        {"name": "我爱竞赛网", "url": "https://www.52jingsai.com/"},
        {"name": "Biendata数据竞赛", "url": "https://www.biendata.xyz/"},
        {"name": "Coggle竞赛社区", "url": "https://www.coggle.club/"},
        {"name": "上交教务处", "url": "https://jwc.sjtu.edu.cn/"},
        {"name": "中科大教务处", "url": "https://www.teach.ustc.edu.cn/"},
        {"name": "北大教务部", "url": "https://dean.pku.edu.cn/"},
    ],
    "max_items_per_push": 20,
    "deadline_alert_days": 14,
    "data_file": "data/state.json",
    "http_timeout": 30,
    "kaggle_username": "",
    "kaggle_key": "",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

_ENV_MAP = {
    "FEISHU_WEBHOOK": "feishu_webhook",
    "FEISHU_SECRET": "feishu_secret",
    "FEISHU_CHAT_ID": "feishu_chat_id",
    "FEISHU_SHEET_URL": "feishu_sheet_url",
    "LARK_PROFILE": "lark_profile",
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
    known = {"tianchi", "datafountain", "nowcoder", "xfyun", "kaggle", "saikr", "ctftime"}
    out = []
    for s in sources:
        s = (s or "").strip().lower()
        if s in known:
            out.append(s)
    return out
