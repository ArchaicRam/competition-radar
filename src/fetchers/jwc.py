# -*- coding: utf-8 -*-
"""高校教务处「竞赛通知」抓取器（第一手情报源）。

## 为什么需要它

现有 8 个 fetcher 覆盖的是天池/牛客/赛氪/CTFtime 这类**平台接口**，
产出几乎全是企业赛与众测（实测 state.json 285 行里，众测平台 42 行，
而"高校教务处"来源只有 3 行 = 1%）。

但高校教务处是全链路里**信息密度最高、最容易解析**的一类源：
- 纯静态 HTML，无 JS 渲染，一个 GET 拿到全部条目
- 每篇通知正文必然写明「报名截止时间」「校内选拔时间」「省赛/国赛时间」
- 天然带主办方与官方链接，可作 `evidence_url`

实测：西安交大「竞赛安排」列表页一页同时给出蓝桥杯(12-18)、工创赛(校赛11-13)、
美赛(校内11-19)、智能汽车(11月启动)、华为ICT 五项 A 类赛的准确日期。

## 结构

    列表页 → 抽 <a> 锚点（标题 + href + 日期）
           → 过滤：标题命中赛事关键词（蓝桥杯/挑战杯/报名/选拔…）
           → 详情页 → 正则抽「报名…截止 2026年12月18日」并判定口径
           → Competition(platform="jwc·<学校>", evidence_url=详情页, deadline=…, deadline_kind=…)

## 配置

config.json 增加：

    "sources": [..., "jwc"],
    "jwc_seeds": [
      {"university": "西安交通大学", "list_url": "http://dean.xjtu.edu.cn/jxxx/jxtz2/jsap.htm"},
      ...
    ],
    "jwc_max_per_site": 12,      # 每站最多取几条通知详情（控制请求量）
    "jwc_fetch_detail": true     # 关掉则只用列表页标题，不抓正文（更快但没日期）

种子也可以用独立 JSON 文件：`"jwc_seeds_file": "data/jwc_seeds.json"`。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from .. import http
from ..models import Competition
from .base import BaseFetcher

log = logging.getLogger("jwc")

# 只收"像竞赛通知"的标题，避免把教务处的选课/考试通知也抓进来
_INCLUDE_KEYS = (
    "竞赛", "大赛", "挑战赛", "选拔赛", "报名", "参赛", "赛区", "总决赛",
)
# 明显不是竞赛通知的标题
_EXCLUDE_KEYS = (
    "选课", "调课", "停课", "考试安排", "监考", "成绩", "学籍", "毕业",
    "推免", "转专业", "教材", "培养方案", "教学质量", "招生",
    "招募", "培训", "讲座", "论坛", "宣讲", "公示", "名单",
    # 成果报道类（教务处栏目里常混入，如"我校学子获佳绩""教研竞赛双丰收"）
    "喜报", "获佳绩", "丰收", "纪实", "风采", "我校学子", "获奖", "斩获",
)

# 从通知正文里抽「报名…截止」的日期
_DATE_RE = re.compile(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")

# 一段文本里出现这些词，说明该句在讲"报名/提交截止"
_REG_DEADLINE_HINTS = (
    "报名截止", "报名时间", "截止时间", "报名期", "报名通道", "截止日期",
    "提交", "申报", "报送", "发送", "材料",
)
# 讲"校内选拔"的上下文
_CAMPUS_HINTS = ("校内", "学校报名", "校赛", "学院报名", "本单位", "校内选拔", "各学院")
# 讲"作品提交"的上下文
_SUBMIT_HINTS = ("作品提交", "提交作品", "作品申报", "材料提交", "截稿")


class _AnchorParser(HTMLParser):
    """抽 <a> 锚点 + 其周边文本，用于列表页。"""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: List[Tuple[str, str]] = []
        self._href: Optional[str] = None
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = (dict(attrs).get("href") or "").strip()
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._buf).split())
            if text and self._href:
                self.anchors.append((text, self._href))
            self._href = None
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


_BLOCK_TAG_RE = re.compile(
    r"(?is)</?(?:p|div|li|ul|ol|tr|td|th|dt|dd|h[1-6]|table|section|article|"
    r"blockquote|header|footer|form|br)\b[^>]*>"
)


def _strip_tags(html: str) -> str:
    """HTML → 纯文本。

    **只有块级标签换行，行内标签（span/strong/b/em/a/font）直接去掉不换行**。
    这是个容易踩的坑：如果无差别用 `\\n` 替换所有标签，
    `报名截止时间暂定于<strong>2026年11月13日</strong>`
    会被切成两行，日期就和"报名截止"分家了，正则永远抽不到。
    """
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = _BLOCK_TAG_RE.sub("\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)          # 行内标签：无分隔
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _date_tokens(sent: str) -> List[Tuple[int, int, str]]:
    """抽出句子里的全部日期 → [(start, end, 'YYYY-MM-DD')]，支持省略年份的写法。

    「2026年8月31日-11月30日」的后一个日期没有年份，靠前一个推。
    """
    out: List[Tuple[int, int, str]] = []
    last_year: Optional[int] = None
    last_month: Optional[int] = None
    for m in _DATE_TOKEN.finditer(sent or ""):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        if y:
            year = last_year = int(y)
        elif last_year is not None:
            year = last_year
            if last_month is not None and mo < last_month:
                year = last_year + 1          # 跨年：8月-2月
                last_year = year
        else:
            continue
        try:
            iso = datetime(year, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            continue
        last_month = mo
        out.append((m.start(), m.end(), iso))
    return out


def _deadline_candidates(text: str) -> List[Tuple[str, str]]:
    """返回正文里抽到的全部 (日期, 口径) 候选，按文档顺序。"""
    cands: List[Tuple[str, str]] = []
    for sent in re.split(r"[。；;\n]", text or ""):
        if not any(h in sent for h in _REG_DEADLINE_HINTS):
            continue
        toks = _date_tokens(sent)
        if not toks:
            continue
        cand = ""
        # 1) 区间 → 终点
        for i in range(len(toks) - 1):
            between = sent[toks[i][1]:toks[i + 1][0]]
            if _SEP_OK.match(between) and _RANGE_SEP.search(between):
                cand = toks[i + 1][2]
        # 2) 无区间：优先取"截止/截至"之后的第一个日期，否则句中最后一个
        if not cand:
            idx = max(sent.rfind(k) for k in ("截止", "截至"))
            after = [t for t in toks if idx >= 0 and t[0] > idx]
            cand = after[0][2] if after else toks[-1][2]
        if not cand:
            continue
        if any(h in sent for h in _CAMPUS_HINTS):
            kind = "校内报名截止"
        elif any(h in sent for h in _SUBMIT_HINTS):
            kind = "作品提交截止"
        else:
            kind = "报名截止"
        if (cand, kind) not in cands:
            cands.append((cand, kind))
    return cands


def _find_deadline(text: str) -> Tuple[str, str]:
    """从通知正文里取一个"代表截止日期"，返回 (YYYY-MM-DD, 口径)。

    关键点 1 —— **区间必须取终点**：「报名时间：2026年10月8日—2026年12月18日」
    的真实截止是 12-18，取第一个日期会得到 10-08（开报日），
    这类错误会让"还剩 6 周"变成"已经过期"，是这类抽取器最容易犯的错。

    关键点 2 —— **一篇通知常含多个赛道的多个截止**（蓝桥杯：软件赛 12-18、
    专项赛 11-30、视觉艺术/数字科技 次年 4-26）。单值无法表达，策略是：
        有校内截止 → 取**最早的校内截止**（这才是真正卡住用户的那道闸）
        否则       → 取**最晚的报名/提交截止**（宁可说"还能报"，不能说"已过期"）
    其余截止不丢弃，由 `_deadline_options()` 一并挂在 deadline_alt 上。
    """
    cands = _deadline_candidates(text)
    if not cands:
        return "", ""
    campus = [d for d, k in cands if k == "校内报名截止"]
    if campus:
        return min(campus), "校内报名截止"
    top = max(cands, key=lambda x: x[0])
    return top[0], top[1]


def _deadline_options(text: str, limit: int = 4) -> str:
    """把全部候选截止压成一行，如 ``2026-12-18(报名截止);2027-04-26(作品提交截止)``。"""
    cands = sorted(set(_deadline_candidates(text)), key=lambda x: x[0])
    if len(cands) <= 1:
        return ""
    return ";".join(f"{d}({k})" for d, k in cands[:limit])


_DATE_TOKEN = re.compile(r"(?:(20\d{2})\s*[年\-/.]\s*)?(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")
_RANGE_SEP = re.compile(r"[—\-–~～至到]")
_SEP_OK = re.compile(r"^[\s\-—–~～至到:：]*$")


def _clean_title(t: str) -> str:
    """把「[竞赛安排]关于组织参加2027年美国大学生数学建模竞赛相关工作的通知」洗成赛名。

    还要去掉标题里混进来的日期——各校列表页有三种写法：
      · 湖南大学：`222026-10`（=10月22日，`{DD}{YYYY-MM}` 无分隔符拼接）
      · 多数学校：`2026-03-30`、`2026/3/30`
      · 部分学校把日期拼在标题**开头或末尾**
    不去掉的话，标题会变成「222026-10 2026年XX大赛…」，既难看又让关键词匹配失准。
    """
    t = re.sub(r"^(\[[^\]]{1,8}\]\s*)+", "", t or "")            # 去 [竞赛安排] 之类栏目前缀
    # 去开头/结尾的日期（含湖南大学 DDYYYY-MM 这种畸形格式）
    t = re.sub(r"^\s*\d{1,2}(20\d{2})[-/.](\d{1,2})\s+", "", t)
    t = re.sub(r"^\s*20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*[:：]?\s*", "", t)
    t = re.sub(r"\s*[(（]?\s*20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\s*[)）]?\s*$", "", t)
    t = re.sub(r"^关于(组织参加|组织|举办|开展|做好|参加|转发|公布|印发)*", "", t)
    # 去掉开头的学校名："武汉大学关于组织参加2026年…" → "2026年…"
    t = re.sub(r"^[\u4e00-\u9fa5]{2,10}(大学|学院|学校|学部)关于(组织参加|组织|举办|开展|做好|参加)*", "", t)
    t = re.sub(r"^(报名参加|关于参加)", "", t)
    t = re.sub(r"(相关)?(工作)?的通知.*$", "", t)
    t = re.sub(r"(暂定|另行通知)$", "", t)
    t = re.sub(r"\s*[|｜-]\s*$", "", t)
    return t.strip(" ：:·-—、")


def _mk(**kw) -> Optional[Competition]:
    """构造 Competition，自动丢弃当前 models 里不存在的字段（兼容未打补丁的版本）。"""
    known = set(getattr(Competition, "__dataclass_fields__", {}))
    base = {k: v for k, v in kw.items() if k in known}
    extra = {k: v for k, v in kw.items() if k not in known}
    if "title" not in base or not base.get("title"):
        return None
    comp = Competition(**base)
    for k, v in extra.items():                       # dataclass 无 slots，可挂附加属性
        try:
            setattr(comp, k, v)
        except Exception:                            # noqa: BLE001
            pass
    return comp


class JwcFetcher(BaseFetcher):
    """高校教务处竞赛通知 → Competition。"""

    platform = "jwc"

    def fetch(self) -> List[Competition]:
        seeds = self._seeds()
        if not seeds:
            log.info("[jwc] 未配置 jwc_seeds，跳过")
            return []
        out: List[Competition] = []
        max_detail = int(self.cfg.get("jwc_max_per_site", 12))
        want_detail = bool(self.cfg.get("jwc_fetch_detail", True))
        include_stale = bool(self.cfg.get("jwc_include_stale", False))
        skipped = 0
        for seed in seeds:
            uni = (seed.get("university") or "").strip()
            url = (seed.get("list_url") or seed.get("url") or "").strip()
            if not url:
                continue
            # 种子清单里已实测失败(verified=False)或栏目停更(stale=True)的直接跳过，
            # 不浪费请求——这两类现成结论是实测出来的，没必要每天再撞一次墙
            if seed.get("verified") is False:
                skipped += 1
                continue
            if seed.get("stale") and not include_stale:
                skipped += 1
                continue
            try:
                out.extend(self._one_site(uni, url, max_detail, want_detail))
            except Exception as e:                    # noqa: BLE001
                log.warning("[jwc:%s] 失败: %s", uni, e)
        log.info("[jwc] 共 %d 条（跳过 %d 个不可用/停更源）", len(out), skipped)
        return out

    # -- 内部 -------------------------------------------------------------

    def _seeds(self) -> List[Dict[str, Any]]:
        seeds = self.cfg.get("jwc_seeds")
        if isinstance(seeds, list) and seeds:
            return seeds
        path = (self.cfg.get("jwc_seeds_file") or "").strip()
        if path:
            try:
                raw = json.loads(open(path, encoding="utf-8").read())
                return raw.get("seeds") or raw or []
            except Exception as e:                    # noqa: BLE001
                log.warning("[jwc] 读取种子文件失败 %s: %s", path, e)
        return []

    def _one_site(self, uni: str, list_url: str, max_detail: int, want_detail: bool) -> List[Competition]:
        status, raw, _h = http.get(list_url, headers=self._headers(), timeout=self._timeout())
        if status != 200:
            raise RuntimeError(f"列表页 HTTP {status}")
        html = _decode(raw)
        p = _AnchorParser()
        try:
            p.feed(html)
        except Exception:                             # noqa: BLE001
            pass

        picked: List[Tuple[str, str]] = []
        for text, href in p.anchors:
            if href.startswith(("javascript:", "#", "mailto:")) or len(text) < 8:
                continue
            if any(k in text for k in _EXCLUDE_KEYS):
                continue
            if not any(k in text for k in _INCLUDE_KEYS):
                continue
            absu = urljoin(list_url, href)
            if absu not in [u for _t, u in picked]:
                picked.append((text, absu))
            if len(picked) >= max_detail:
                break

        out: List[Competition] = []
        for text, absu in picked:
            deadline, kind, evidence, alt = "", "", absu, ""
            if want_detail:
                try:
                    st2, raw2, _h2 = http.get(absu, headers=self._headers(), timeout=self._timeout())
                    if st2 == 200:
                        body = _strip_tags(_decode(raw2))
                        deadline, kind = _find_deadline(body)
                        alt = _deadline_options(body)
                except Exception as e:                # noqa: BLE001
                    log.warning("[jwc:%s] 详情页失败 %s: %s", uni, absu, e)
            title = _clean_title(text)
            if not title:
                continue
            comp = _mk(
                key=f"jwc:{uni}:{absu}"[-180:],
                title=title,
                platform=f"jwc·{uni}",
                organizer="",
                url=absu,
                deadline=deadline,
                comp_type="综合",
                status="报名中" if deadline else "未公布",
                enabled_date="",
                evidence_url=evidence,          # 需 models 增字段
                deadline_kind=kind,             # 需 models 增字段
                deadline_alt=alt,               # 需 models 增字段（同通知里的其它口径截止）
                confidence="B",                 # B = 高校教务处转发（A = 主办方官网原文）
            )
            if comp is not None:
                out.append(comp)
        log.info("[jwc:%s] 通知 %d 条，其中 %d 条抽到报名截止",
                 uni, len(out), sum(1 for c in out if c.deadline))
        return out
