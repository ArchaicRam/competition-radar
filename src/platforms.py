# -*- coding: utf-8 -*-
"""各平台来源信息（用于"消息来源"标注）。"""
from __future__ import annotations

from typing import Dict, Tuple

# platform -> (展示名, 来源页面地址)
# 展示名全中文（DataFountain/Kaggle 无官方中文名，用描述性中文）
SOURCE_INFO: Dict[str, Tuple[str, str]] = {
    "tianchi": ("阿里云天池", "https://tianchi.aliyun.com/competition/programmingList"),
    "datafountain": ("数据竞赛平台", "https://www.datafountain.cn/competitions"),
    "nowcoder": ("牛客竞赛", "https://ac.nowcoder.com/acm/contest/calendar"),
    "xfyun": ("科大讯飞开发者大赛", "https://challenge.xfyun.cn/"),
    "kaggle": ("全球算法竞赛", "https://www.kaggle.com/competitions"),
    "ctftime": ("CTF赛事日历", "https://ctftime.org/events"),
    "saikr": ("赛氪竞赛网（暂未接入）", "https://www.saikr.com/contests"),
}

PLATFORM_NAMES: Dict[str, str] = {k: v[0] for k, v in SOURCE_INFO.items()}
