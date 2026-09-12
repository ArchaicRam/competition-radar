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
    "大学生创新创业", "国际大学生创新", "挑战杯", "ACM", "ICPC", "CCPC",
    "数学建模", "电子设计", "计算机设计大赛", "蓝桥杯", "天梯赛",
    "大数据挑战赛", "移动应用创新", "网络技术挑战", "信息安全竞赛",
    "服务外包", "软件杯", "软件创新", "物联网设计", "集成电路",
    "智能汽车", "智能车", "机器人大赛", "RoboMaster", "RoboCup",
    "三创赛", "电子商务", "计算机博弈",
    # 学校竞赛目录补漏（计算机相关、含金量可）
    "工程实践与创新能力", "程序设计竞赛", "嵌入式", "智能机器人",
    "机器人及人工智能", "RoboCom", "青年创客", "BIM", "大唐杯", "西门子杯",
    # 中国高等教育学会"全国普通高校大学生竞赛目录"（2025 版 84 项）计算机相关补全
    "中国高校计算机大赛",        # C4：天梯/大数据/移动应用/网络技术/AI创意五赛道
    "系统能力大赛",              # CCF 全国大学生计算机系统能力大赛（编译/OS/数据库）
    "软件测试大赛",              # 观察目录
    "计算机能力挑战赛",          # 全国高校计算机能力挑战赛（观察目录）
    "计算机应用能力与信息素养",  # 观察目录
    "数字媒体科技作品",          # 观察目录
    "研究生电子设计", "研电赛",  # 研究生创新实践系列大赛（学位中心指导）
    "信息安全与对抗",
    "码蹄杯", "ican大学生",      # iCAN 用 "ican大学生" 匹配，避免误命中 American 等
    "睿抗", "RAICOM", "机器人开发者", "中国机器人大赛",
    "三维数字化", "工行杯", "校园人工智能算法", "金砖国家技能",
    "开源之夏",                  # 中科院软件所主办，非目录但权威
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
# 评分模型（用户规则）：业界认可(+3) > 部委/工信部认可(+2) > 名声大(+1)
#   - 总分 >=3 → 高（业界认可本身，或 部委认可+名声大）
#   - 总分 1~2 → 中（仅部委认可，或仅名声大）
#   - 0 分 → 走平台/主办方默认规则；答题类等低质模式一律 低
RATING_COLOR = {"高": "#E02020", "中": "#E67E22", "低": "#2ECC40"}

# 业界认可：知名企业、权威学会、顶级/业界公认赛事（权重 3）
_INDUSTRY_KEYS = [
    "阿里巴巴", "阿里云", "腾讯", "华为", "百度", "科大讯飞", "字节", "美团", "京东",
    "蚂蚁", "微软", "Google", "Kaggle", "大疆", "网易", "小米",
    "ACM", "ICPC", "CCPC", "CCF", "IEEE", "中国计算机学会", "中国人工智能学会", "中国电子学会",
    "中国高校计算机大赛", "系统能力大赛",
    "中国工业与应用数学学会", "中国工程院", "中国科学院", "北京大学", "清华大学",
    "蓝桥杯", "数学建模", "挑战杯", "国际大学生创新", "天梯赛", "RoboMaster",
    "RoboCup", "计算机设计大赛", "信息安全竞赛", "中国软件杯", "软件杯", "华为ICT",
    "金砖", "服务外包", "创客中国", "数据要素", "智能汽车", "电子设计",
    "西门子杯",  # 西门子=业界认可
]

# 部委/政府认可（权重 2）：工信部、教育部、科技部等
_GOV_KEYS = ["工信部", "工业和信息化部", "教育部", "科技部", "共青团", "中央网信办", "国务院", "中央"]

# 名声大但未必业界认可（权重 1）。
# 注意："互联网+"不是业界认可关键词（同名赛事含金量差异大），
# 教育部办的"互联网+"大赛靠"国际大学生创新/大学生创新创业"+教育部 命中为高，
# 协会办的"互联网+技能应用赛"靠 AI 评级兜底为中。
_FAME_KEYS = ["全国高校计算机能力", "大学生职业发展", "全国大学生科技", "大学生创新创业"]


# 低含金量标题模式：答题/知识竞赛类（常见"报名费+刷题+发证"收割模式），
# 无论 LLM 怎么评级都按低处理（AI 发现时直接剔除）
LOW_VALUE_TITLE_PATTERNS = ("知识竞赛", "答题", "问答", "闯关", "知识科普")


def is_low_value(title: str = "") -> bool:
    return any(k in (title or "") for k in LOW_VALUE_TITLE_PATTERNS)


# 与计算机/科技主题明显无关的标题关键词（外语/人文/文体类）。
# 综合类聚合站（我爱竞赛网、赛氪等）和 LLM 提取都会漏进这类条目，
# 这里做确定性兜底：命中即剔除，不依赖 LLM 自觉。
_OFF_TOPIC_TITLE_KEYS = [
    # 外语类
    "外语", "英语", "词汇", "翻译", "日语", "法语", "德语", "俄语", "韩语",
    "泰语", "西班牙语", "阿拉伯语", "涉外",
    # 人文/语言表达类
    "演讲", "朗诵", "辩论", "征文", "写作", "作文", "文学", "诗词", "诗歌",
    "普通话", "口译", "笔译",
    # 文体/传媒类
    "书法", "绘画", "摄影", "短视频", "微电影", "配音", "主持", "导游",
    "声乐", "舞蹈", "歌唱", "动漫",
]

# 科技属性覆盖：标题含这些词时不按跑题处理（如"AI 英语口语训练平台开发赛"）
_TECH_OVERRIDE_KEYS = [
    "编程", "程序设计", "代码", "算法", "人工智能", "AI", "大模型", "LLM",
    "大数据", "数据挖掘", "数据分析", "软件", "计算机", "网络安全", "信息安全",
    "黑客", "机器人", "物联网", "嵌入式", "芯片", "集成电路", "智能车",
    "数学建模", "电子设计",
]


def is_off_topic(title: str = "", organizer: str = "", platform: str = "") -> bool:
    """标题明显属于外语/人文/文体类且无任何科技属性 → 与本项目无关。

    仅用于综合来源（AI 发现 / 赛氪等聚合站）；
    tianchi/xfyun/datafountain/kaggle 等技术平台本身只发数据/AI 赛事，
    标题里的"翻译""词汇"等词多为 NLP 任务名，不做跑题过滤。
    """
    if (platform or "").split("·")[0] in ("tianchi", "xfyun", "datafountain", "kaggle"):
        return False
    t = title or ""
    if any(k in t for k in _TECH_OVERRIDE_KEYS):
        return False
    return any(k in t for k in _OFF_TOPIC_TITLE_KEYS)


def prestige(title: str = "", organizer: str = "", platform: str = "", rating: str = "") -> str:
    """含金量：高 / 中 / 低。

    规则评分优先（用户标准：业界认可>部委认可>名声大）：
    规则能识别出信号（score>=1）就以规则为准，不被 AI 评级覆盖；
    AI 评级只在规则无信号（score==0）时兜底。
    """
    if is_low_value(title):
        return "低"
    t = title or ""
    org = organizer or ""
    # 练手/练习/周赛/月赛类：练习性质，一律低
    if any(k in t for k in ("练手", "练习赛", "周赛", "月赛", "入门", "新手")):
        return "低"
    score = 0
    if any(k in org or k in t for k in _INDUSTRY_KEYS):
        score += 3  # 业界认可
    if any(k in org for k in _GOV_KEYS):
        score += 2  # 部委/工信部认可
    if any(k in t for k in _FAME_KEYS):
        score += 1  # 名声大
    if score >= 3:
        return "高"
    if score >= 1:
        return "中"
    # 规则无信号：用 AI 评级兜底，再走平台/主办方默认
    r = (rating or "").strip()
    if r in ("高", "中", "低"):
        return r
    if platform == "nowcoder":
        return "中" if any(k in t for k in ("多校", "挑战", "邀请赛", "省赛", "区域赛")) else "低"
    if platform == "tianchi" and not org:
        # 天池上无主办方信息的赛事：学习/练手/新人/实战类降级，其余视为阿里系正规赛事
        if any(k in t for k in ("新人", "实战", "教学", "Baseline", "练手", "学习")):
            return "低"
        if any(k in t for k in ("打榜", "系列赛")):
            return "中"
        return "高"
    if platform == "kaggle":
        return "高"  # 国际公认平台（主办方为空时）
    # 有主办方的：按主办方性质默认（大学/协会/研究院挂的课题 → 中，不再因平台无脑高）
    if any(k in org for k in ("协会", "学会", "研究会", "研究院", "大学", "学院", "中心", "省", "市")):
        return "中"
    return "中"


def normalize_org(name: str) -> str:
    """主办方名称归一化：去掉公司后缀，用于分组聚合。"""
    s = (name or "").strip()
    for suf in _ORG_SUFFIXES:
        s = s.replace(suf, "")
    return s.strip() or "其他"


_RATING_RANK = {"高": 0, "中": 1, "低": 2}


def competition_sort_key(c) -> Tuple:
    """排序键：(是否官方, 含金量高→低, 归一化主办方, 截止日期)。

    官方赛事优先 -> 含金量（高>中>低）-> 同一主办方聚合 -> 截止日期升序。
    """
    official_flag = 0 if is_official(c.title, c.organizer) else 1
    rating = prestige(c.title, c.organizer, c.platform, c.rating)
    rating_rank = _RATING_RANK.get(rating, 1)
    org = normalize_org(c.organizer)
    dl = (c.deadline or "").strip()
    return (official_flag, rating_rank, org, (0, dl) if dl else (1, ""))


def sort_competitions(comps: List) -> List:
    return sorted(comps, key=competition_sort_key)
