# -*- coding: utf-8 -*-
"""教育部认定（A 类）竞赛识别、主办方归并、排序规则。

排序优先级：
  1. 教育部 A 类赛事（关键词命中，如蓝桥杯/ICPC/挑战杯…）优先
  2. 同一主办方聚合在一起（主办方名称做了归一化，去掉"有限公司"等后缀）
  3. 组内按截止日期升序（无截止日期的排最后）
"""
from __future__ import annotations

import re
from typing import List, Tuple

# 教育部认可的全国性大学生竞赛常见名称/简称（可按需在 config.json 的 official_keywords 覆盖）
OFFICIAL_KEYWORDS: List[str] = [
    "互联网+", "国际大学生创新", "挑战杯", "ACM", "ICPC", "CCPC",
    "数学建模", "电子设计", "计算机设计大赛", "蓝桥杯", "天梯赛",
    "大数据挑战赛", "移动应用创新", "网络技术挑战", "信息安全竞赛",
    "服务外包", "软件杯", "软件创新", "物联网设计", "集成电路",
    "智能汽车", "智能车", "机器人大赛", "RoboMaster", "RoboCup",
    "三创赛", "电子商务", "计算机博弈",
]

_ORG_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "股份公司")


def is_official(title: str, organizer: str = "") -> bool:
    """标题或主办方命中教育部 A 类赛事关键词。"""
    text = f"{title or ''} {organizer or ''}".lower()
    return any(kw.lower() in text for kw in OFFICIAL_KEYWORDS)


def categorize(title: str, organizer: str = "", platform: str = "") -> str:
    """赛事类别（全中文）：官方赛事 / 企业赛 / 在线赛 / 高校赛事 / 其他。"""
    if is_official(title, organizer):
        return "官方赛事"
    if platform.startswith("AI发现"):
        org = organizer or ""
        if any(k in org for k in ("公司", "集团", "科技", "研究院", "银行", "中心")):
            return "企业赛"
        if any(k in org for k in ("大学", "学院", "学校")):
            return "高校赛事"
        return "其他"
    if platform in ("tianchi", "datafountain", "xfyun", "kaggle"):
        return "企业赛"
    if platform == "nowcoder":
        return "在线赛"
    return "其他"


# 类型/赛道英文 -> 中文（各平台接口常吐英文或缩写）
_TYPE_CN = {
    "algorithem": "算法", "algorithm": "算法",
    "ai": "人工智能", "nlp": "自然语言处理", "cv": "计算机视觉",
    "data": "数据", "datamining": "数据挖掘", "recsys": "推荐系统",
    "speech": "语音识别", "audio": "音频", "image": "图像",
    "text": "文本", "video": "视频", "multimodal": "多模态",
    "llm": "大模型", "skill": "技能", "agent": "智能体",
    "segmentation": "图像分割", "classification": "分类",
    "application": "应用", "train": "训练",
}

# 零宽字符（来源数据里常见，肉眼不可见但会污染单元格显示）
_ZERO_WIDTH = "\u200b\u200c\u200d\u200e\u200f\ufeff"


def clean_text(s) -> str:
    """清理文本：去掉零宽/控制字符、压缩空白。"""
    if s is None:
        return ""
    s = str(s)
    for ch in _ZERO_WIDTH:
        s = s.replace(ch, "")
    return " ".join(s.split())


def normalize_comp_type(s) -> str:
    """把类型/赛道字段里的英文统一成中文，并清理零宽字符。"""
    s = clean_text(s)
    if not s:
        return ""
    if s.isascii() and not any(c.isdigit() for c in s):
        # 纯英文 token（如 algorithem）
        return _TYPE_CN.get(s.lower(), s)
    # 混合如 "Skill技能开发"：英文前缀翻译，若中文部分已含该词则直接去掉前缀
    m = re.match(r"^([A-Za-z]+)(.*)$", s)
    if m:
        en, rest = m.group(1).lower(), m.group(2)
        cn = _TYPE_CN.get(en)
        if cn:
            return rest if cn in rest else cn + rest
        return s
    return s


# 含金量评级（高/中/低）与颜色（高=红、中=橙、低=绿）
RATING_COLOR = {"高": "#E02020", "中": "#E67E22", "低": "#2ECC40"}

_HIGH_ORG_KEYWORDS = [
    "教育部", "工信部", "科技部", "共青团", "国务院", "中央", "中国科学院", "中国工程院",
    "中国计算机学会", "中国人工智能学会", "中国电子学会", "中国软件行业协会", "ACM", "IEEE",
    "阿里巴巴", "阿里云", "腾讯", "华为", "百度", "科大讯飞", "字节", "美团", "京东",
    "蚂蚁", "微软", "Google", "Kaggle", "北京大学", "清华大学", "浙江大学", "上海交通大学",
]


# 低含金量标题模式：答题/知识竞赛类（常见"报名费+刷题+发证"收割模式），
# 无论 LLM 怎么评级都按低处理（AI 发现时直接剔除）
LOW_VALUE_TITLE_PATTERNS = ("知识竞赛", "答题", "问答", "闯关", "知识科普")


def is_low_value(title: str = "") -> bool:
    return any(k in (title or "") for k in LOW_VALUE_TITLE_PATTERNS)


def prestige(title: str = "", organizer: str = "", platform: str = "", rating: str = "") -> str:
    """含金量：高 / 中 / 低。AI 已评级的直接用；其余按主办方/名称规则推算。"""
    r = (rating or "").strip()
    if r in ("高", "中", "低"):
        return r
    if is_low_value(title):
        return "低"
    if is_official(title, organizer):
        return "高"
    org = organizer or ""
    if any(k in org for k in _HIGH_ORG_KEYWORDS):
        return "高"
    t = title or ""
    if any(k in t for k in ("练手", "练习赛", "周赛", "月赛", "入门", "新手")):
        return "低"
    if platform == "nowcoder":
        return "中" if any(k in t for k in ("多校", "挑战", "邀请赛", "省赛", "区域赛")) else "低"
    # 知名平台赛事（阿里/讯飞/Kaggle 等主办，主办方字段常为空）
    if platform in ("tianchi", "kaggle", "xfyun"):
        return "高"
    if any(k in org for k in ("协会", "学会", "研究会", "委员会", "研究院", "大学", "学院", "省", "市", "中心")):
        return "中"
    return "中"


def normalize_org(name: str) -> str:
    """主办方名称归一化：去掉公司后缀，用于分组聚合。"""
    s = (name or "").strip()
    for suf in _ORG_SUFFIXES:
        s = s.replace(suf, "")
    return s.strip() or "其他"


def competition_sort_key(c) -> Tuple:
    """排序键：(是否官方, 归一化主办方, 截止日期)。"""
    official = 0 if is_official(c.title, c.organizer) else 1
    org = normalize_org(c.organizer)
    dl = (c.deadline or "").strip()
    return (official, org, (0, dl) if dl else (1, ""))


def sort_competitions(comps: List) -> List:
    return sorted(comps, key=competition_sort_key)
