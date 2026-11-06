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
    # 网络安全专项（部委/权威机构主办的知名安全赛事）
    "强网杯", "网鼎杯", "长城杯", "铁人三项", "天网杯",
    "ISCC", "工业信息安全", "汽车安全攻防", "数据安全技能", "数字安全",
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
    "强网杯", "网鼎杯", "长城杯", "铁人三项",
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


def is_irrelevant(title: str = "", platform: str = "") -> bool:
    """统一的相关性兜底：跑题（语言/文科/设计/招募公告等）一律剔除；
    知识竞赛类低质模式只作用于聚合来源——技术平台（天池/讯飞等）的
    "问答""答疑"是合法 NLP 任务名，不做低质过滤。"""
    if is_off_topic(title, platform=platform):
        return True
    if (platform or "").split("·")[0] in ("tianchi", "xfyun", "datafountain", "kaggle", "ctftime"):
        return False
    return is_low_value(title)


def concrete_stage(status: str = "", deadline: str = "") -> str:
    """阶段列规范化：只允许具体状态，绝不输出"待核实"或空值（硬性要求）。

    - 已是具体状态（报名中/进行中/未开始…）→ 原样保留
    - "待核实"/空值：有有效截止日期 → "报名中"；无截止或截止不可解析 → "进行中"
      （"待人工复核"的语义由来源标注"AI发现·站点名"承担，不占用阶段列）
    """
    from datetime import datetime

    s = (status or "").strip()
    # 历史数据里可能残留旧逻辑写下的"预计3月启动报名（按往届）"——
    # 那是按往届月份推的，不能当状态用（会让人以为能报名），一律归"未公布"。
    if any(k in s for k in ("按往届", "预计")):
        return "未公布"
    if s and s != "待核实":
        return s
    d = (deadline or "").strip()
    if not d:
        # 没有截止日期就老实写"未公布"。原来兜底成"进行中"，
        # 会让"其实还没开报名"的赛事看起来像已经在跑。
        return "未公布"
    if d:
        try:
            if datetime.strptime(d[:10], "%Y-%m-%d").date() >= datetime.now().date():
                return "报名中"
        except ValueError:
            return "未公布"
    return "已截止"


# 与计算机/科技主题明显无关的标题关键词（外语/人文/文体类）。
# 综合类聚合站（我爱竞赛网、赛氪等）和 LLM 提取都会漏进这类条目，
# 这里做确定性兜底：命中即剔除，不依赖 LLM 自觉。
_OFF_TOPIC_TITLE_KEYS = [
    # 外语类
    "外语", "英语", "词汇", "翻译", "日语", "法语", "德语", "俄语", "韩语",
    "泰语", "西班牙语", "阿拉伯语", "涉外", "跨文化",
    "外研社", "外教社", "国才杯", "NECCS",
    # 人文/语言表达类（含中语言文字类）
    "演讲", "朗诵", "辩论", "征文", "写作", "作文", "文学", "诗词", "诗歌",
    "普通话", "口译", "笔译", "语言文字", "汉语", "诵读", "规范字",
    "诵写讲", "经典诵", "诗词大会",
    # 文体/传媒类
    "书法", "绘画", "摄影", "短视频", "微电影", "配音", "主持", "导游",
    "声乐", "舞蹈", "歌唱", "动漫",
]

# 与计算机"稍有关系但技术性弱"的赛（商科/文科/设计/职业类）以及
# 根本不是比赛的公告（招募/招聘）——同样确定性剔除。
_WEAK_TECH_TITLE_KEYS = [
    # 商科/营销/文科
    "跨境电商", "外贸", "市场营销", "市场调查", "营销", "直播", "带货",
    "广告艺术", "新文科", "金融挑战", "投资理财",
    # 设计类（视觉/媒体，技术性弱）
    "数字交互媒体", "媒体设计", "视觉传达", "平面设计", "包装设计",
    "环境设计", "服装设计", "影视", "编导",
    # 职业发展/综合技能（非技术赛道为主）
    "职业发展", "职业规划", "职业生涯", "职业院校技能", "求职",
    "创青春", "技能应用赛", "办公应用",
    # 纯考试类数学（数学建模保留，编程强相关）
    "数学竞赛",
    # 不是比赛的公告
    "招募", "宣传大使", "校园大使", "协办院校", "联合招聘", "招聘会",
    "双选会", "夏季招聘", "秋季招聘",
]

# 科技属性覆盖：标题含这些词时不按跑题处理（如"AI 英语口语训练平台开发赛"）
_TECH_OVERRIDE_KEYS = [
    "编程", "程序设计", "代码", "算法", "人工智能", "AI", "大模型", "LLM",
    "大数据", "数据挖掘", "数据分析", "软件", "计算机", "网络安全", "信息安全",
    "黑客", "机器人", "物联网", "嵌入式", "芯片", "集成电路", "智能车",
    "数学建模", "电子设计",
]

# 艺术 / 设计 / 影视传媒类：用户明确要求不进表（含 AIGC 短剧、海报、插画等）。
# 注意**不能写裸的"设计"或"视觉"**——"集成电路设计""计算机视觉"会被误杀；
# 所以这里只收"组合词"，且该判定**优先于** _TECH_OVERRIDE_KEYS 与目录放行：
# 目录内的 大广赛、华灿奖、蓝桥杯视觉艺术设计赛 一样按艺术类剔除。
_ART_TITLE_KEYS = [
    # 美术 / 造型
    "艺术", "美术", "绘画", "书法", "雕塑", "篆刻",
    # 视觉设计
    "视觉传达", "视觉艺术", "视觉设计", "平面设计", "包装设计",
    "海报", "插画", "版式", "字体设计", "标志设计", "logo设计",
    # 环境 / 服饰 / 工业设计
    "环境设计", "环境艺术", "室内设计", "景观设计", "服装设计", "服饰设计",
    "工业设计", "产品设计", "文创设计", "文创产品", "非遗", "传统工艺", "民间艺术",
    # 影视传媒 / 内容创作
    "影视", "编导", "微电影", "短视频", "纪录片", "宣传片",
    "短剧", "漫剧", "微短剧", "剧本", "分镜",
    # 数字艺术 / 新媒体
    "数字艺术", "数字媒体", "新媒体艺术", "交互艺术", "动画", "动漫",
    "摄影", "图片创意", "AI绘画", "AI生图", "AIGC绘画",
    # 赛事品牌（本身就是艺术设计类）
    "华灿奖", "大广赛", "广告艺术", "广告设计", "学院奖",
]


def is_art(title: str = "") -> bool:
    """是否艺术/设计/影视传媒类赛（用户要求：这类不进表）。"""
    t = title or ""
    return any(k in t for k in _ART_TITLE_KEYS)


def is_off_topic(title: str = "", organizer: str = "", platform: str = "") -> bool:
    """标题明显属于外语/人文/文体类，或属于技术性弱的商科/设计/职业类，
    或根本是招募/招聘公告 → 与本项目无关。

    艺术/设计/影视传媒类（含 AIGC 短剧、海报、插画等）按用户要求**一律剔除**，
    且该判定优先于技术平台豁免、科技词覆盖与目录放行——因为
    "AI 微短剧赛"含 AI、"华灿奖/大广赛/蓝桥杯视觉艺术设计赛"在目录内，
    任何一条放行规则都会把它们漏进来。

    其余规则仅用于综合来源（AI 发现 / 赛氪等聚合站）；
    tianchi/xfyun/datafountain/kaggle/ctftime 等技术平台本身只发技术赛事，
    标题里的"翻译""词汇"等词多为 NLP 任务名，不做跑题过滤。
    """
    t = title or ""
    # ① 艺术类：最高优先级，任何来源都不放行
    if is_art(t):
        return True
    # ② 技术平台豁免（平台本身只发技术赛）
    if (platform or "").split("·")[0] in ("tianchi", "xfyun", "datafountain", "kaggle", "ctftime"):
        return False
    if any(k in t for k in _TECH_OVERRIDE_KEYS):
        return False
    # 外语/人文/文体类：**即使在高教学会目录内也剔除**。
    # 目录的 84 项里有"外研社·国才杯""外教社杯跨文化能力大赛""大广赛"这类，
    # 对计算机社团毫无价值；此前"目录内一律放行"会把它们放进来。
    if any(k in t for k in _OFF_TOPIC_TITLE_KEYS):
        return True
    # 目录内赛事放行"技术性弱"这一类（避免"数学竞赛"把《全国大学生数学竞赛》误杀）
    try:
        from . import official_registry as _reg

        if _reg.lookup(t, organizer):
            return False
    except Exception:  # noqa: BLE001  目录不可用时退回纯规则
        pass
    if any(k in t for k in _WEAK_TECH_TITLE_KEYS):
        return True
    return False


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
    if platform == "ctftime":
        # CTFtime 登记的 CTF：强网杯等国内权威赛会被标题规则命中为高，
        # 其余国际赛事默认中（含重量级如 Google CTF 也无从规则判断）
        return "中"
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


# ==========================================================================
# 目录驱动覆盖（放在文件末尾，模块导入完即生效）
#
# 背景：上面的"关键词 substring"判定会双向出错——
#   假阳性：is_official("某某杯大学生数学建模大赛", "某某民营公司") = True
#   假阴性：教育部高教司主办的节能减排竞赛被判成"其他"
# 现改为以《全国普通高校大学生竞赛分析报告》竞赛目录为准（见 official_registry）。
# 旧的三个实现保留为 _legacy_*，随时可回滚。
# ==========================================================================
from . import official_registry as _reg  # noqa: E402

_legacy_is_official = is_official
_legacy_categorize = categorize
_legacy_prestige = prestige


def is_official(title, organizer="", **_kw):  # noqa: F811
    """是否官方赛事：目录内，或部委/中央群团主办。"""
    return _reg.is_official(title or "", organizer or "")


def categorize(title, organizer="", platform=""):  # noqa: F811
    """赛事类别：官方赛事 / 企业赛 / 在线赛 / 高校赛事 / 其他。"""
    return _reg.categorize(title or "", organizer or "", platform or "")


def prestige(title="", organizer="", platform="", rating=""):  # noqa: F811
    """含金量：高 / 中 / 低（目录优先，其次主办方权威度，最后平台默认）。"""
    return _reg.prestige(title or "", organizer or "", platform or "", rating or "")


def is_competition(title=""):
    """是不是一场竞赛（测评/认证/培训/夏令营不算）。"""
    return _reg.is_competition(title or "")


def catalog_id(title, organizer=""):
    """权威目录里的赛事 id，用于把子赛道折叠到父赛事。"""
    return _reg.catalog_id(title or "", organizer or "")


def deadline_kind_of(text, default="报名截止"):
    """从通知原文判断日期属于哪种口径（全国/校内/作品提交/比赛结束）。"""
    return _reg.classify_deadline_kind(text or "", default)

