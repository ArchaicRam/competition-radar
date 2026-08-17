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
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urlparse

from . import http, llm
from .models import Competition
from .official import clean_text, is_low_value

log = logging.getLogger("ai_discover")

_SYSTEM_PROMPT = (
    "你是竞赛情报员。根据给定的网页文本，提取其中面向大学生或社会开放的"
    "比赛、挑战赛、黑客松、创新大赛、需求征集、揭榜挂帅、作品征集类活动。\n"
    "规则：\n"
    "- 只提取网页中真实出现的活动，不要编造\n"
    "- **只保留与计算机/软件/数据/AI/电子/网络安全/创新创业相关**的活动，无关的不要输出\n"
    "- 类型用中文：比赛 / 挑战赛 / 黑客松 / 需求征集 / 揭榜挂帅 / 作品征集\n"
    "- 每条给出含金量 rating：\"高\"（国家级/部委/顶尖企业/权威学会主办，或奖金丰厚、影响力大）/ "
    "\"中\"（省级/行业协会/一般企业主办）/ \"低\"（纯商业营销性质、主办方不知名或野鸡、"
    "获奖即付费的割韭菜类）\n"
    "- **注意：很多正规比赛（如蓝桥杯、数学建模）需要报名费，付费本身不代表含金量低**\n"
    "- **含金量为\"低\"或主办方明显不知名的不要输出**\n"
    "- 最多输出 **10 条**最重要的活动\n"
    "- 只输出一个 JSON 对象：{\"items\": [{\"title\": \"活动标题\", "
    "\"organizer\": \"主办方\", \"type\": \"类型\", \"deadline\": \"报名截止，可空\", "
    "\"reward\": \"奖励/奖金，可空\", \"url\": \"报名链接，可空\", "
    "\"intro\": \"一句话简介，可空\", \"rating\": \"高\"}]}\n"
    "- 无有效活动时输出 {\"items\": []}"
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
    # 无年份："8月31日" -> 今年
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{datetime.now().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def site_name(url: str) -> str:
    host = urlparse(url).netloc
    return host.replace("www.", "").split(".")[0]


def discover(seed_sources: List[Dict[str, str]], cfg: Dict[str, Any]) -> List[Competition]:
    """扫描种子源，返回 AI 发现的比赛列表。seed_sources: [{"name","url"}, ...]"""
    api_key = (cfg.get("llm_api_key") or "").strip()
    if not api_key:
        log.info("未配置 llm_api_key，AI 情报员跳过")
        return []
    out: List[Competition] = []
    timeout = int(cfg.get("http_timeout", 30))
    for src in seed_sources or []:
        url = (src.get("url") or "").strip()
        name = (src.get("name") or site_name(url)).strip()
        if not url:
            continue
        try:
            status, raw, _ = http.get(url, timeout=timeout)
            if status != 200:
                log.warning("[AI:%s] 抓取失败 status=%s", name, status)
                continue
            text, anchors = extract_page(raw)
            if len(text) < 80:
                log.warning("[AI:%s] 页面文本过短(%d)，跳过", name, len(text))
                continue
            items = _extract(text, url, cfg)
            for it in items:
                comp = _to_competition(it, url, name, anchors)
                if comp is not None:
                    out.append(comp)
            log.info("[AI:%s] 发现 %d 条（锚点 %d 个）", name, len(items), len(anchors))
        except Exception as e:  # noqa: BLE001
            log.warning("[AI:%s] 失败: %s", name, e)
    return out


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
    # 答题/知识竞赛类硬过滤（不依赖 LLM 评级）
    if is_low_value(title):
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
        status="待核实",
        enabled_date="",
        rating=rating,
    )


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
