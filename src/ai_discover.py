# -*- coding: utf-8 -*-
"""AI 情报员：从"非接口型"来源页面（官网公告/聚合站/揭榜挂帅页）提炼比赛与需求征集。

工作方式：
  1. 抓取种子源页面（自动识别编码：HTTP 头 charset -> meta charset -> utf-8 -> gb18030）
  2. HTML 转纯文本（去掉脚本/样式）
  3. 交给 LLM 提取结构化条目（标题/主办方/类型/截止/奖励/链接/简介）
  4. 规范化日期后生成 Competition，来源标注为 "AI发现·站点名"

注意：AI 发现的结果是"情报线索"，建议人工复核后再组织报名。
"""
from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urlparse

from . import http, llm
from .models import Competition
from .official import clean_text, is_low_value, is_off_topic

log = logging.getLogger("ai_discover")

_SYSTEM_PROMPT = (
    "你是竞赛情报员。根据给定的网页文本，提取其中面向大学生或社会开放的"
    "比赛、挑战赛、黑客松、创新大赛、需求征集、揭榜挂帅、作品征集，"
    "以及**学生可参与获取经验的其他机会**：开源活动（如开源之夏、GSoC）、"
    "训练营、众包悬赏、项目招募等。\n"
    "规则：\n"
    "- 只提取网页中真实出现的活动，不要编造\n"
    "- **只保留与计算机/软件/数据/AI/电子/网络安全/创新创业相关，且技术性强**的活动，无关的不要输出\n"
    "- **以下类型绝对不要输出**：语言/文字/写作/诵读/普通话/汉语类，外语/翻译类，"
    "纯考试型数学/英语竞赛，跨境电商/营销/直播/新文科等商科文科类，"
    "职业规划/职业发展/求职类，视觉/媒体/服装等设计类，"
    "以及任何\"招募\"\"招聘\"\"宣传大使\"\"协办院校\"类公告（这些不是比赛）\n"
    "- 类型用中文：比赛 / 挑战赛 / 黑客松 / 需求征集 / 揭榜挂帅 / 作品征集 / "
    "开源活动 / 训练营 / 众包悬赏 / 项目招募\n"
    "- 每条给出含金量 rating：\"高\"（国家级/部委/顶尖企业/权威学会主办，或奖金丰厚、影响力大）/ "
    "\"中\"（省级/行业协会/一般企业主办）/ \"低\"（纯商业营销性质、主办方不知名或野鸡、"
    "获奖即付费的割韭菜类）\n"
    "- **注意：很多正规比赛（如蓝桥杯、数学建模）需要报名费，付费本身不代表含金量低**\n"
    "- **含金量为\"低\"或主办方明显不知名的不要输出**\n"
    "- 最多输出 **10 条**最重要的活动\n"
    "- 只输出一个 JSON 对象：{\"items\": [{\"title\": \"活动标题\", "
    "\"organizer\": \"主办方\", \"type\": \"类型\", \"deadline\": \"报名截止，可空\", "
    "\"reward\": \"奖励/奖金，可空\", \"url\": \"报名链接，可空\", "
    "\"intro\": \"一句话简介，可空\", \"rating\": \"高\", "
    "\"stage\": \"活动阶段：报名中/进行中/已结束，从页面判断，看不出留空\"}]}\n"
    "- **页面明确写着已结束、获奖名单公示、已颁奖的不要输出**\n"
    "- 无有效活动时输出 {\"items\": []}"
)

# 阶段核实提示词：对阶段不确定的条目，抓详情页让 LLM 判断（DeepSeek 单条几分钱）
_VERIFY_PROMPT = (
    "你是竞赛信息审核员。根据给定网页文本，判断该活动**现在**处于什么阶段。\n"
    "规则：\n"
    "- 页面明确写着已结束、获奖名单/获奖公示、颁奖典礼已举行、赛程已完结 → \"已结束\"\n"
    "- 正在报名/征集作品/开放组队，且未过截止 → \"报名中\"\n"
    "- 活动已开始进行（比赛进行中、训练营已开营、公示期中）→ \"进行中\"\n"
    "- 页面内容与该活动无关，或完全看不出阶段 → \"无关\"\n"
    "- 若页面给出报名/提交截止日期，一并提取为 YYYY-MM-DD，没有则留空\n"
    "- 若页面中出现了该活动的**官方网站/官方报名页**链接（主办方自建域名，"
    "而非新闻站/聚合站/公众号页面），提取为 official_url；没有则留空\n"
    "只输出一个 JSON 对象：{\"stage\": \"报名中\", \"deadline\": \"\", \"official_url\": \"\"}"
)

# 已知的第三方聚合站域名：AI 提取到的官网链接若来自这些站点，视为非官网
_AGGREGATOR_HOSTS = (
    "52jingsai.com", "saikr.com", "52jingsai.net",
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0
        self.anchors: List[tuple] = []  # [(链接文本, href)]
        self._a_href = None
        self._a_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "iframe"):
            self._skip += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "td"):
            self.parts.append("\n")
        if tag == "a":
            self._a_href = dict(attrs).get("href")
            self._a_text = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "iframe") and self._skip:
            self._skip -= 1
        if tag == "a":
            if self._a_href:
                t = " ".join("".join(self._a_text).split())
                if t:
                    self.anchors.append((t, self._a_href))
            self._a_href = None

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)
            if self._a_href is not None:
                self._a_text.append(data)


def extract_page(raw: bytes, max_chars: int = 6000):
    """返回 (纯文本, [(链接文本, href), ...])。"""
    text = _decode(raw)
    p = _TextExtractor()
    try:
        p.feed(text)
    except Exception:  # noqa: BLE001
        pass
    cleaned = " ".join("".join(p.parts).split())
    return cleaned[:max_chars], p.anchors


def html_to_text(raw: bytes, max_chars: int = 6000) -> str:
    return extract_page(raw, max_chars)[0]


def _decode(raw: bytes) -> str:
    # 1) 尝试 utf-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # 2) 从 HTML meta 找 charset
    head = raw[:4096].decode("ascii", "ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    if m:
        try:
            return raw.decode(m.group(1))
        except (LookupError, UnicodeDecodeError):
            pass
    # 3) GBK/GB18030（中文站点常见）
    for enc in ("gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


_DATE_PATTERNS = [
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日?", lambda g: f"{g[0]}-{int(g[1]):02d}-{int(g[2]):02d}"),
    (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda g: f"{g[0]}-{int(g[1]):02d}-{int(g[2]):02d}"),
]


def normalize_date(s) -> str:
    from datetime import datetime

    s = clean_text(s)
    if not s:
        return ""
    for pat, fmt in _DATE_PATTERNS:
        m = re.search(pat, s)
        if m:
            return fmt(m.groups())
    # 无年份："8月31日" -> 今年；若已过去超过 45 天，视为去年的公告、归到明年
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            now = datetime.now()
            dt = datetime(now.year, int(m.group(1)), int(m.group(2)))
            if (now - dt).days > 45:
                dt = datetime(now.year + 1, int(m.group(1)), int(m.group(2)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def site_name(url: str) -> str:
    host = urlparse(url).netloc
    return host.replace("www.", "").split(".")[0]


def discover(seed_sources: List[Dict[str, str]], cfg: Dict[str, Any]) -> List[Competition]:
    """扫描种子源，返回 AI 发现的比赛列表。seed_sources: [{"name","url"}, ...]

    各种子源互相独立，并行抓取+提炼（每个种子 = 1 次抓页 + 1 次 LLM 调用，
    种子多时串行会显著拖长总耗时）。
    """
    api_key = (cfg.get("llm_api_key") or "").strip()
    if not api_key:
        log.info("未配置 llm_api_key，AI 情报员跳过")
        return []
    tasks = []
    for src in seed_sources or []:
        url = (src.get("url") or "").strip()
        name = (src.get("name") or site_name(url)).strip()
        if url:
            tasks.append((name, url))
    out: List[Competition] = []
    if not tasks:
        return out
    with ThreadPoolExecutor(max_workers=6) as pool:
        for comps in pool.map(_discover_one, [(name, url, cfg) for name, url in tasks]):
            out.extend(comps)

    # 阶段核实：阶段不确定的条目抓详情页让 LLM 判断（页面写"已结束"的直接剔除）。
    # 这是防"早结束的比赛还躺在表里"的关键环节——列表页文本里通常没有逐条的阶段信息
    # 链接指向聚合站的条目无论阶段是否明确都进核实：顺带提取官网链接替换聚合站链接
    def _needs_verify(c: Competition) -> bool:
        if not (c.url or "").startswith("http"):
            return False
        if not (c.status or "").strip():
            return True
        host = (urlparse(c.url).netloc or "").lower()
        return any(a in host for a in _AGGREGATOR_HOSTS)

    uncertain = [c for c in out if _needs_verify(c)]
    if uncertain:
        log.info("AI 阶段核实：%d 条需要核实，逐条读详情页判断", len(uncertain))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(_verify_one, [(c, cfg) for c in uncertain]))
        gone = {id(c) for c in results if c is None}
        out = [c for c in out if id(c) not in gone]
        log.info("AI 阶段核实完成：剔除 %d 条，剩余 %d 条", len(gone), len(out))
    return out


def _verify_one(task: tuple) -> Optional[Competition]:
    """读条目详情页，让 LLM 判断当前阶段。返回 None 表示应剔除。"""
    comp, cfg = task
    timeout = int(cfg.get("http_timeout", 30))
    try:
        status, raw, _ = http.get(comp.url, timeout=timeout)
        if status != 200:
            log.warning("[AI核实] %s 抓取失败 status=%s（保留，走兜底阶段）", comp.title, status)
            return comp
        text, _anchors = extract_page(raw, max_chars=4000)
        if len(text) < 80:
            return comp
        user = f"活动：{comp.title}\n来源页面：{comp.url}\n\n网页文本：\n{text}\n\n请判断该活动当前阶段并输出 JSON。"
        resp = llm.chat_json(
            [
                {"role": "system", "content": _VERIFY_PROMPT},
                {"role": "user", "content": user},
            ],
            cfg,
            max_tokens=300,
        )
        stage = str(resp.get("stage") or "").strip() if isinstance(resp, dict) else ""
        dl = normalize_date(resp.get("deadline")) if isinstance(resp, dict) else ""
        if dl and not comp.deadline:
            comp.deadline = dl
        # 官网链接优先：详情页里出现主办方自建域名时，替换掉聚合站/种子页链接
        if isinstance(resp, dict):
            official_url = str(resp.get("official_url") or "").strip()
            if official_url.startswith("http") and _is_better_link(official_url, comp.url):
                comp.url = official_url
        if stage in ("已结束", "无关"):
            log.info("[AI核实] %s —— %s，剔除", comp.title, stage)
            return None
        if stage in ("报名中", "进行中"):
            comp.status = stage
        return comp
    except Exception as e:  # noqa: BLE001
        # 核实失败不拦数据：保留条目，阶段由 postprocess 兜底成具体状态
        log.warning("[AI核实] %s 失败（保留）: %s", comp.title, e)
        return comp


def _discover_one(task: tuple) -> List[Competition]:
    name, url, cfg = task
    timeout = int(cfg.get("http_timeout", 30))
    try:
        status, raw, _ = http.get(url, timeout=timeout)
        if status != 200:
            log.warning("[AI:%s] 抓取失败 status=%s", name, status)
            return []
        text, anchors = extract_page(raw)
        if len(text) < 80:
            log.warning("[AI:%s] 页面文本过短(%d)，跳过", name, len(text))
            return []
        items = _extract(text, url, cfg)
        comps = []
        for it in items:
            comp = _to_competition(it, url, name, anchors)
            if comp is not None:
                comps.append(comp)
        log.info("[AI:%s] 发现 %d 条（锚点 %d 个）", name, len(comps), len(anchors))
        return comps
    except Exception as e:  # noqa: BLE001
        log.warning("[AI:%s] 失败: %s", name, e)
        return []


def _extract(text: str, url: str, cfg: Dict[str, Any]) -> List[dict]:
    user = f"网页地址：{url}\n\n网页文本：\n{text}\n\n请提取活动信息并输出 JSON。"
    resp = llm.chat_json(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        cfg,
        max_tokens=int(cfg.get("llm_max_tokens", 3000)),
    )
    if isinstance(resp, dict):
        items = resp.get("items") or []
    elif isinstance(resp, list):
        items = resp
    else:
        items = []
    return [i for i in items if isinstance(i, dict)]


def _to_competition(it: dict, page_url: str, site: str, anchors: List[tuple] = None) -> Optional[Competition]:
    from datetime import datetime

    title = clean_text(it.get("title"))
    if not title:
        return None
    # 提取阶段：页面已明确写"已结束"的直接剔除（不靠后续兜底）
    stage = clean_text(it.get("stage"))
    if stage == "已结束":
        return None
    status = stage if stage in ("报名中", "进行中") else ""
    # 答题/知识竞赛类硬过滤（不依赖 LLM 评级）
    if is_low_value(title):
        return None
    # 外语/人文/文体类硬过滤（LLM 提示词约束不可靠，这里确定性兜底）
    if is_off_topic(title):
        return None
    org = clean_text(it.get("organizer"))
    comp_type = clean_text(it.get("type")) or "其他"
    deadline = normalize_date(it.get("deadline"))
    # 已截止的不收（避免把往届比赛当新情报）
    if deadline:
        try:
            if datetime.strptime(deadline, "%Y-%m-%d") < datetime.now():
                return None
        except ValueError:
            pass
    reward = clean_text(it.get("reward"))
    # 含金量：AI 评级，低的不收（过滤"偏文/野鸡"）
    rating = clean_text(it.get("rating"))
    if rating not in ("高", "中", "低"):
        rating = ""
    if rating == "低":
        return None
    # 报名链接：优先锚点匹配（页面内真实链接）> LLM 给的链接 > 页面本身
    link = _match_anchor(title, anchors or [], page_url)
    if not link:
        llm_url = clean_text(it.get("url"))
        link = llm_url if llm_url.startswith("http") else page_url
    key = hashlib.md5(f"{title}|{page_url}".encode("utf-8")).hexdigest()[:12]
    return Competition(
        key=f"ai:{key}",
        title=title,
        platform=f"AI发现·{site}",
        organizer=org,
        url=link,
        deadline=deadline,
        reward=reward,
        comp_type=comp_type,
        status=status,  # 空表示阶段不确定，后续核实/兜底补成具体状态
        enabled_date="",
        rating=rating,
    )


def _is_better_link(new_url: str, old_url: str) -> bool:
    """判断新链接是否比旧链接更适合作为报名入口（官网 > 聚合站/种子页）。"""
    from urllib.parse import urlparse

    def host(u: str) -> str:
        return (urlparse(u).netloc or "").lower().replace("www.", "", 1) if u else ""

    old_host, new_host = host(old_url), host(new_url)
    if not new_host or new_host == old_host:
        return False
    # 旧链接是聚合站/资讯站 → 任何不同域名的新链接都更优
    if any(h in old_host for h in _AGGREGATOR_HOSTS):
        return True
    # 旧链接是种子源首页（根路径）而新链接是深层页面 → 更优
    if old_url and not urlparse(old_url).path.strip("/"):
        return True
    return False


_ANCHOR_SKIP = ("javascript:", "mailto:", "tel:", "#")


def _match_anchor(title: str, anchors: List[tuple], page_url: str) -> str:
    """在页面锚点里找与标题最匹配的链接（归一化后相等或互相包含）。"""
    from urllib.parse import urljoin

    def norm(s):
        return re.sub(r"[\s“”\"'《》【】「」…（）()·．.]+", "", s or "")

    nt = norm(title)
    if not nt:
        return ""
    best, best_score = "", 0
    for t, href in anchors:
        href = (href or "").strip()
        if not href or any(href.startswith(k) for k in _ANCHOR_SKIP):
            continue
        nt2 = norm(t)
        if not nt2 or len(nt2) < 4:
            continue
        if nt2 == nt:
            return urljoin(page_url, href)
        if len(nt) >= 6 and (nt in nt2 or nt2 in nt):
            score = min(len(nt), len(nt2))
            if score > best_score:
                best_score = score
                best = urljoin(page_url, href)
    return best
