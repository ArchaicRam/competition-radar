# -*- coding: utf-8 -*-
"""目录驱动的赛事识别（替换 official.py 里的 substring 关键词判定）。

## 为什么要换

旧实现 `official.is_official()` 是「标题或主办方命中 60 个关键词之一 → 官方赛事」，
带来两类对称的错误（均已在真实数据上复现）：

    假阳性： is_official("某某杯大学生数学建模大赛", "某某民营公司") = True
    假阴性： 第二十届全国大学生节能减排社会实践与科技竞赛（教育部高教司主办）
             → categorize() = "其他"

## 新实现的三层判定

    第 1 层  目录精确匹配：以《全国普通高校大学生竞赛分析报告》竞赛目录
             （主目录 + 观察目录）为唯一权威，用"长别名 + 主办方白名单"双重命中。
    第 2 层  主办方权威度：目录未覆盖时，看主办方是否为部委/中央群团/国家级学会。
    第 3 层  负向规则：主办方是"促进会/报社/文化传播/N 人小公司"这类，
             即使标题含"全国""大学生""数学建模"也一律不算官方。

## 用法（drop-in 替换）

    # 原来
    from . import official
    official.is_official(t, o)
    # 换成
    from . import official_registry as official
    official.is_official(t, o)          # 签名完全一致

`load_catalog()` 在模块导入时惰性执行一次；找不到 catalog 文件时自动降级回
`official` 的旧逻辑（不会崩，只是回到旧精度）。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("official_registry")

# 目录文件默认位置：src/registry_catalog.json（与 config.json 同级的 data/ 亦可）
_DEFAULT_CATALOG_NAMES = ("registry_catalog.json",)

# ==========================================================================
# 主办方权威度词表
# ==========================================================================

# 部委 / 中央群团 / 国家级机构：主办即高含金量
_NATIONAL_AUTHORITY = (
    "教育部", "工业和信息化部", "工信部", "科学技术部", "科技部",
    "共青团中央", "中国科协", "中国科学技术协会", "中央网信办",
    "国家发展改革委", "国家发改委", "人力资源社会保障部", "商务部",
    "国务院", "中央统战部", "中国科学院", "中国工程院",
    "中国社会科学院", "全国学联", "国家自然科学基金",
    "教育部高等教育司", "教育部高等教育司", "教育部学位与研究生教育发展中心",
)

# 省级：中
_PROVINCIAL = ("省教育厅", "省教委", "团省委", "省科协", "市教育局", "省工业和信息化厅")

# 反面：常见"市场化赛事"主办方特征。命中即不算官方（除非目录明确收录）
_NEGATIVE_ORGANIZER = (
    "促进会", "文化传播", "文化发展", "传媒有限公司", "教育科技有限公司",
    "咨询有限公司", "某某", "报社", "杂志社", "出版社", "广告",
    "人才交流中心", "培训中心", "人才服务中心",
)

# 目录内但主办方是学会：仍按目录走（中国图学学会/中国自动化学会等）
_ACADEMIC = ("学会", "协会", "研究会", "联合会", "联盟", "专业委员会", "工作委员会")


# ==========================================================================
# 目录加载
# ==========================================================================

_CATALOG: Optional[Dict[str, Any]] = None
_ALIAS_INDEX: List[Tuple[str, Dict[str, Any]]] = []   # [(归一化别名, event)]，按长度降序


def _norm(s: str) -> str:
    """标题/别名归一化：全角转半角、去引号书名号括号空格、去零宽。"""
    if not s:
        return ""
    out = []
    for ch in str(s):
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"[\s“”\"'《》【】「」\[\]（）()·．.,，、:：!！?？/\\|_—\-]+", "", s)
    return s.lower()


def _catalog_path(explicit: Optional[str] = None) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    here = Path(__file__).resolve().parent
    for name in _DEFAULT_CATALOG_NAMES:
        for cand in (here / name,                   # src/registry_catalog.json
                     here / "src" / name,           # 模块在仓库根时
                     here.parent / "data" / name):  # data/registry_catalog.json
            if cand.is_file():
                return cand
    return None


def load_catalog(path: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """加载并索引目录。失败时返回空目录（后续判定自动降级）。"""
    global _CATALOG, _ALIAS_INDEX
    if _CATALOG is not None and not force:
        return _CATALOG

    catalog: Dict[str, Any] = {"meta": {}, "events": [], "by_id": {}}
    p = _catalog_path(path)
    if p is None:
        log.warning("未找到 registry_catalog.json，目录匹配降级为关键词兜底")
    else:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            events = [e for e in (raw.get("events") or []) if isinstance(e, dict)]
            catalog = {
                "meta": raw.get("meta") or {},
                "events": events,
                "by_id": {e.get("id"): e for e in events if e.get("id")},
            }
            log.info("赛事目录已加载：%s（%d 项，主目录 %d / 观察 %d）",
                     p.name, len(events),
                     sum(1 for e in events if e.get("list_type") == "main"),
                     sum(1 for e in events if e.get("list_type") == "observe"))
        except Exception as e:  # noqa: BLE001
            log.warning("赛事目录加载失败（%s），降级为关键词兜底: %s", p, e)

    # 建别名索引：标准名 + 全部别名，按归一化长度降序 → 长别名优先（避免短别名截胡）
    # 下限 3：像"蓝桥杯""三创赛""大广赛"这类 3 字本身就是品牌名，不能因太短被丢；
    # 泛化短词的排除靠"目录作者不写进 aliases"来保证，不靠长度阈值。
    idx: List[Tuple[str, Dict[str, Any]]] = []
    for ev in catalog["events"]:
        names = [ev.get("name") or ""] + list(ev.get("aliases") or [])
        for n in names:
            nn = _norm(n)
            if len(nn) >= 3:
                idx.append((nn, ev))
    idx.sort(key=lambda x: -len(x[0]))
    _ALIAS_INDEX = idx
    _CATALOG = catalog
    return catalog


def reload_catalog(path: Optional[str] = None) -> Dict[str, Any]:
    return load_catalog(path, force=True)


# ==========================================================================
# 核心匹配
# ==========================================================================

def _core_name(ev: Dict[str, Any]) -> str:
    """目录条目的"核心中文名"，去掉括号别称与拉丁字母。

    为什么需要：目录里写的是「睿抗机器人开发者大赛（RAICOM）」，归一化后变成
    「睿抗机器人开发者大赛raicom」；而实际标题是「睿抗机器人开发者大赛（RoboCom）
    CAIP信息技术创新赛道」。两边做"完整包含"判断时，因为中文名后面粘了个 raicom
    而永远匹配不上，导致这条目录内赛事被判成「其他/低」。
    """
    name = ev.get("name") or ""
    name = re.sub(r"[（(\[【][^）)\]】]*[）)\]】]", "", name)   # 去掉括号内容
    name = re.sub(r"[A-Za-z][A-Za-z0-9/&\-]*", "", name)      # 去掉残留拉丁词
    return _norm(name)


def lookup(title: str, organizer: str = "") -> Optional[Dict[str, Any]]:
    """在目录里找这条比赛对应的赛事条目。命中返回 event dict，否则 None。

    判定顺序（"名称命中"与"主办方校验"是**加权**关系，不是硬与门）：

      1) 名称命中 + 主办方命中 organizer_ok  → 直接认（最强证据）
      2) 名称命中 + 主办方不在白名单，但**也不是负面主办方** → 认
         （目录的主办方字段本就 60% 未核实，硬与门会把赛事全漏掉）
      3) 名称命中 + 主办方是"促进会/报社/公司"这类负面 →
         若标题里**完整出现该条目的核心中文名**才认（强证据），否则不认

    规则 3 的例外是踩过坑的：睿抗 RoboCom 的主办是「工业和信息化部人才交流中心」，
    而"人才交流中心"在负面词表里（为了挡住挂名发证的野鸡赛）。早先这里一刀切 continue，
    结果把目录内的睿抗也判成了「其他/低」。现在用"核心名完整出现"作为放行条件。

    另外还要求别名 >= 3 字；具体性靠"目录作者不写裸泛化词"保证。
    """
    load_catalog()
    nt = _norm(title)
    if not nt:
        return None
    neg = organizer_authority(organizer) == "negative" if organizer else False
    for alias, ev in _ALIAS_INDEX:
        if alias not in nt:
            continue
        ok_list = [_norm(x) for x in (ev.get("organizer_ok") or []) if x]
        if ok_list and organizer and any(frag in _norm(organizer) for frag in ok_list):
            return ev                                   # (1) 名称 + 主办方双命中
        if neg:
            if _strong_name_match(ev, title, alias):
                return ev            # (3-例外) 标题强证据对上目录标准名 → 放行
            continue                 # (3) 名称像，但主办方负面且只是弱命中 → 不认
        if ev.get("strict_organizer") and organizer:
            continue                                    # 该条目要求主办方必须对上
        return ev                                       # (2) 名称命中、主办方不矛盾
    return None


def catalog_id(title: str, organizer: str = "") -> str:
    """规范赛事 ID（用于把子赛道折叠到父赛事，如传智杯 21 行 → 1 个 parent）。"""
    ev = lookup(title, organizer)
    return str(ev.get("id") or "") if ev else ""


def organizer_authority(organizer: str = "") -> str:
    """主办方权威度：national / provincial / academic / negative / unknown。

    **negative 优先于 national**：部委下属的"人才交流中心""培训中心"这类
    事业单位（如"工业和信息化部人才交流中心"）挂名发证的赛事，不能因为
    字符串里含"工业和信息化部"就被当成部委主办。
    """
    o = organizer or ""
    if not o:
        return "unknown"
    if any(k in o for k in _NEGATIVE_ORGANIZER):
        return "negative"
    if any(k in o for k in _NATIONAL_AUTHORITY):
        return "national"
    if any(k in o for k in _PROVINCIAL):
        return "provincial"
    if any(k in o for k in _ACADEMIC):
        return "academic"
    return "unknown"


# 非竞赛类：测评 / 考试 / 认证 / 培训 / 夏令营。这类条目占表里若干行，
# 但它们没有"报名截止—比赛—评奖"的赛事结构，不该和竞赛混在一起排序。
#
# 实测教训：曾把「职业技能证书-数学建模考试入口」「高校学生数学建模能力测评考试」
# 当赛事收进表里，还标成「官方赛事/高」。原因是词表只写了"测评/等级考试/认证考试"，
# 没覆盖"证书""考试""考试入口"这几种最常见写法。
_NON_COMPETITION_KEYS = (
    # —— 测评 / 考试 / 认证 ——
    "测评", "能力测评", "等级考试", "认证考试", "资格考试", "考试入口",
    "证书", "考证", "职业技能", "职业资格", "等级认证",
    # —— 培训 / 招募 / 非赛事活动 ——
    "夏令营", "冬令营", "培训班", "训练营报名", "宣讲会", "说明会",
    "招新", "招生",
)

# "考试"单独判：真赛事名字里几乎不会出现（都是"全国大学生XX竞赛"），
# 而"XX考试""考试报名""XX考试入口"全是考试类入口，精度足够高。
# 唯一例外是"竞赛"与"考试"同时出现（如"竞赛考试大纲"），此时保留。


def is_competition(title: str = "") -> bool:
    """标题看起来是不是一场竞赛（而非测评/考试/认证/培训）。供 runner 的过滤器调用。"""
    t = title or ""
    if any(k in t for k in _NON_COMPETITION_KEYS):
        return False
    if "考试" in t and "竞赛" not in t:
        return False
    return True


# ==========================================================================
# 对外接口（签名与 official.py 完全一致，可直接替换）
# ==========================================================================

# 媒体主办方：报社/杂志社/出版社办赛一律不算官方。
# 实测：「第五届"数学周报"全国大学生数学建模大赛」主办方字段是空的，
# 但标题里就写着主办媒体名，靠 organizer 字段判不出来，只能看标题。
_MEDIA_SPONSOR_KEYS = (
    "报社", "报业", "杂志社", "出版社", "日报", "晚报", "周报", "商报", "时报",
)


def effective_authority(title: str = "", organizer: str = "") -> str:
    """综合主办方字段与标题里的主办媒体，给出权威度。

    organizer 为空但标题写着「数学周报」「XX日报」这类，按反面处理。
    """
    auth = organizer_authority(organizer)
    if auth == "negative":
        return auth
    if any(k in (title or "") for k in _MEDIA_SPONSOR_KEYS):
        return "negative"
    return auth


def _strong_name_match(ev: Dict[str, Any], title: str, alias: str = "") -> bool:
    """标题是否"强证据"地就是这条目录赛事（不看主办方）。

    强证据 = 满足任一：
      1) 标题里完整出现核心中文名（去掉括号别称后）
      2) 某个别名几乎覆盖了整个标题（>=80% 长度且 >=6 字）
         —— 用于「RoboCom机器人开发者大赛」这种英文优先的别名

    弱证据（只要"标题包含短别名"）不算：那正是「XX杯蓝桥杯技能大赛」被
    民营公司挂名时能蒙混过关的原因。
    """
    nt = _norm(title)
    if not nt:
        return False
    core = _core_name(ev)
    if core and core in nt:
        return True
    cands = [alias] if alias else []
    cands += [ev.get("name") or ""] + list(ev.get("aliases") or [])
    for c in cands:
        na = _norm(c)
        if len(na) >= 6 and na in nt and len(na) >= 0.8 * len(nt):
            return True
    return False


def _catalog_match_trustworthy(ev: Dict[str, Any], title: str, organizer: str) -> bool:
    """目录命中是否可信。

    实测教训：「第三届"中西挑战杯"大学生数学建模大赛」主办是中国西部研究与发展促进会，
    标题里带"数学建模""挑战杯"字样，如果只看别名命中就会放行成「官方赛事/高」。
    所以：主办方一旦命中反面词表，就只认"标题里完整出现目录标准名"这种强证据。
    """
    if effective_authority(title, organizer) != "negative":
        return True
    return _strong_name_match(ev, title)


def is_official(title: str, organizer: str = "") -> bool:
    """是否"官方赛事"（= 在高教学会竞赛目录内，或部委/中央群团主办）。"""
    if not is_competition(title):
        return False
    auth = effective_authority(title, organizer)
    ev = lookup(title, organizer)
    if ev is not None:
        return _catalog_match_trustworthy(ev, title, organizer)
    # 目录未覆盖时：只有部委级主办才算官方；
    # 学会/协会/促进会/报社一律不算（这正是赛氪那批市场化赛的产地）
    return auth == "national"


# 标题以校名开头 → 校级赛事，不是"官方赛事"。
# 锚定在开头，并且「大学/学院」后面排除「生」字，否则
# 「亚太地区大学生数学建模竞赛」「中国大学生计算机设计大赛」会被误判成校赛。
_SCHOOL_TITLE_RE = re.compile(
    r"^(?:\d{4}\s*年)?(?:第[一二三四五六七八九十百零\d]+届)?"
    r"[\u4e00-\u9fa5]{2,12}(?:大学(?!生)|学院(?!生)|学校)"
)

# 标题里带"校内选拔/校赛/校园赛/选拔赛" → 这一行是学校那一级，不是国赛本身。
# 注意这类条目常常能命中目录别名（如"江苏大学第三届大学生统计建模大赛"命中统计建模大赛），
# 但你能报名的是校赛，标成「官方赛事」会误导，应归「高校赛事」。
_SCHOOL_ROUND_RE = re.compile(
    r"校内选拔|校内赛|校园赛|校赛|校选|学校选拔|选拔赛|校园选拔"
)


def _looks_like_school_event(title: str) -> bool:
    t = (title or "").strip()
    return bool(_SCHOOL_TITLE_RE.match(t)) or bool(_SCHOOL_ROUND_RE.search(t))


def categorize(title: str, organizer: str = "", platform: str = "") -> str:
    """赛事类别（全中文）：官方赛事 / 企业赛 / 在线赛 / 高校赛事 / 其他 / 非竞赛。"""
    if not is_competition(title):
        return "非竞赛"          # 测评/考试/认证/培训：不是赛事，不该混进表里
    auth = effective_authority(title, organizer)
    # 校赛/校内选拔：即使能命中目录别名，你能报的也只是学校那一级，
    # 标「官方赛事」会给出错误信号（"这条是国赛"）。
    if _looks_like_school_event(title):
        return "高校赛事"
    ev = lookup(title, organizer)
    if ev is not None and _catalog_match_trustworthy(ev, title, organizer):
        return "官方赛事"
    if auth in ("national", "provincial"):
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
    # 校名开头/含校名且无"全国/中国/国际"字样：这是校赛，不是官方赛事
    if _looks_like_school_event(title):
        return "高校赛事"
    return "其他"


_INDUSTRY_KEYS = (
    "阿里巴巴", "阿里云", "腾讯", "华为", "百度", "科大讯飞", "字节", "美团", "京东",
    "蚂蚁", "微软", "Google", "Kaggle", "大疆", "网易", "小米",
    "ACM", "ICPC", "CCPC", "CCF", "IEEE", "中国计算机学会", "中国人工智能学会", "中国电子学会",
)

_LOW_VALUE_PATTERNS = ("知识竞赛", "答题", "问答", "闯关", "知识科普")


def prestige(title: str = "", organizer: str = "", platform: str = "", rating: str = "") -> str:
    """含金量：高 / 中 / 低。

    评分依据（按用户规则：业界认可 > 部委认可 > 名声大），但**目录优先**：

        目录主目录(A) 命中            → 高
        部委/中央群团主办             → 高
        目录观察目录(B) 命中          → 中（主办方是部委则仍高）
        省级 / 学会 / 协会            → 中
        知名企业 / 顶级学会           → 高
        练手/周赛/知识竞赛/主办方负面 → 低
        其余                          → 中
    """
    t = title or ""
    o = organizer or ""

    # —— 硬性压低 ——
    if not is_competition(t):
        return "低"
    if any(k in t for k in _LOW_VALUE_PATTERNS):
        return "低"
    if any(k in t for k in ("练手", "练习赛", "周赛", "月赛", "入门", "新手", "热身")):
        return "低"

    auth = effective_authority(t, o)
    if auth == "national":
        return "高"                                  # 部委主办即高（旧逻辑这里只给"中"，是倒挂主因）
    if auth == "negative":
        # 主办方是促进会/报社/公司：除非目录明确收录且名称对得上，一律低
        ev = lookup(t, o)
        if ev is not None and _catalog_match_trustworthy(ev, t, o):
            return "中"
        return "低"

    ev = lookup(t, o)
    if ev is not None:
        grade = (ev.get("official_grade") or "").upper()
        list_type = (ev.get("list_type") or "").lower()
        if grade == "A" or list_type == "main":
            return "高"
        if grade == "B" or list_type == "observe":
            return "中"

    if auth == "provincial":
        return "中"
    if any(k in o or k in t for k in _INDUSTRY_KEYS):
        return "高"

    # —— 平台默认（保留原实现的合理部分）——
    # 这几家是"平台自办/自审"的赛事，平台即背书；与赛氪那种"聚合站转载"不同。
    if platform == "tianchi" and not o:
        if any(k in t for k in ("新人", "实战", "教学", "Baseline", "练手", "学习")):
            return "低"
        if any(k in t for k in ("打榜", "系列赛")):
            return "中"
        return "高"
    if platform == "kaggle":
        return "高"
    if platform == "nowcoder":
        return "中" if any(k in t for k in ("多校", "挑战", "邀请赛", "省赛", "区域赛")) else "低"
    if platform == "ctftime":
        return "中"

    r = (rating or "").strip()
    if r in ("高", "中", "低"):
        return r
    return "中"


# ==========================================================================
# 报名截止口径（解决"官网 1-28 / 校内 11-19"混轴问题）
# ==========================================================================

DEADLINE_KINDS = ("报名截止", "校内报名截止", "作品提交截止", "比赛结束", "未公布")

_KIND_RULES = (
    ("校内报名截止", ("校内", "学校报名", "校赛报名", "学院报名", "本单位", "校内选拔")),
    ("作品提交截止", ("作品提交", "提交作品", "作品申报", "材料提交", "截稿", "提交截止")),
    ("比赛结束", ("比赛结束", "赛事结束", "决赛结束", "比赛时间", "举办", "举行", "开赛")),
    ("报名截止", ("报名截止", "报名时间", "报名期", "截止报名", "报名通道")),
)


def classify_deadline_kind(text: str, default: str = "报名截止") -> str:
    """从通知原文里判断这个日期属于哪种截止口径。

    例：「报名时间自即日起，至2026年11月19日24时」   → 校内报名截止（若上下文含"校内"）
        「作品网上提交 2027-05-20 16:00 前」          → 作品提交截止
    """
    t = text or ""
    for kind, keys in _KIND_RULES:
        if any(k in t for k in keys):
            return kind
    return default


def stage_for(deadline: str = "", kind: str = "", today: Optional[str] = None) -> str:
    """阶段判定：**不再把"没有截止日期"强行写成"报名中"**。

    有截止且未过期 → 报名中；无截止 → 未公布（旧实现写"进行中"，会误导）。
    """
    from datetime import date, datetime

    if today:
        now = datetime.strptime(today, "%Y-%m-%d").date()
    else:
        now = date.today()
    d = (deadline or "").strip()
    if not d:
        return "未公布"
    try:
        dl = datetime.strptime(d[:10], "%Y-%m-%d").date()
    except ValueError:
        return "未公布"
    if dl < now:
        return "已结束" if kind == "比赛结束" else "已截止"
    return "报名中"
