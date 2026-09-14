#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存量官网链接回填：把 state.json 里 AI 发现、但链接指向第三方聚合站的条目，
逐条抓取聚合页并让 LLM 找出该比赛的官方网站/报名页链接，校验后替换。

新发现的条目在 ai_discover._verify_one 中已自动做这件事；
本脚本用于一次性修正历史存量。可重复执行（幂等：已是官网域名的跳过）。

用法：
  python scripts/backfill_official_urls.py            # 实际执行
  python scripts/backfill_official_urls.py --dry-run  # 只看会改什么
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import http, llm  # noqa: E402
from src.ai_discover import _AGGREGATOR_HOSTS, _is_better_link, extract_page  # noqa: E402
from src.config import load_config  # noqa: E402

_PROMPT = (
    "你是竞赛信息审核员。下面是一个竞赛聚合网站上《{title}》页面的文本和页面内链接列表。\n"
    "请找出该比赛**官方网站或官方报名页**的链接（主办方自建域名，"
    "不要新闻网站、公众号文章、其他聚合站的链接）。\n"
    "优先从 links 列表里挑；如果正文里出现了明确的官网 URL 也可以用。\n"
    "找不到就输出空字符串。只输出 JSON：{{\"official_url\": \"\"}}\n\n"
    "links:\n{links}\n\n页面文本：\n{text}"
)


def _host(u: str) -> str:
    return (urlparse(u or "").netloc or "").lower().replace("www.", "", 1)


def _is_aggregator(url: str) -> bool:
    h = _host(url)
    return any(a in h for a in _AGGREGATOR_HOSTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not (cfg.get("llm_api_key") or "").strip():
        sys.exit("未配置 llm_api_key，无法回填")

    with open(args.state, encoding="utf-8") as f:
        state = json.load(f)
    comps = state["competitions"]

    targets = [
        (k, v) for k, v in comps.items()
        if v.get("platform", "").startswith("AI发现")
        and _is_aggregator(v.get("url", ""))
    ]
    print(f"待回填 {len(targets)} 条（链接指向聚合站）")
    fixed = skipped = 0
    for key, v in targets:
        title, old_url = v.get("title", ""), v.get("url", "")
        try:
            status, raw, _ = http.get(old_url, timeout=int(cfg.get("http_timeout", 30)))
            if status != 200:
                print(f"  ✗ 抓取失败 HTTP {status}: {title[:36]}")
                skipped += 1
                continue
            text, anchors = extract_page(raw, max_chars=3500)
            links = "\n".join(f"- {t}: {h}" for t, h in anchors[:40]) or "（无）"
            resp = llm.chat_json(
                [{"role": "user", "content": _PROMPT.format(title=title, links=links, text=text)}],
                cfg, max_tokens=200,
            )
            new_url = str(resp.get("official_url") or "").strip() if isinstance(resp, dict) else ""
            if new_url.startswith("http") and _is_better_link(new_url, old_url):
                print(f"  ✓ {title[:36]}\n      {old_url}\n      -> {new_url}")
                if not args.dry_run:
                    v["url"] = new_url
                fixed += 1
            else:
                print(f"  - 未找到官网链接: {title[:40]}")
                skipped += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {title[:36]} —— {e}")
            skipped += 1

    if not args.dry_run and fixed:
        with open(args.state, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"\n完成：回填 {fixed} 条，跳过 {skipped} 条{'' if args.dry_run else '，state.json 已更新'}")


if __name__ == "__main__":
    main()
