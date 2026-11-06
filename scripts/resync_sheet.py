# -*- coding: utf-8 -*-
"""不重新抓取，只用 state.json 里已有的数据重算并重写飞书表格 / Excel。

用途：改了后处理规则（过滤、折叠、口径、排序、配色）之后，想立刻看到效果，
      又不想把 30 多个源重抓一遍（那要 10 分钟）。

用法：
    python scripts/resync_sheet.py              # 重算 + 写飞书表 + 写 Excel
    python scripts/resync_sheet.py --dry-run    # 只打印将要写入的内容摘要
    python scripts/resync_sheet.py --excel-only # 只重写本地 Excel，不动飞书表
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config                 # noqa: E402
from src.excel_export import export_excel          # noqa: E402
from src.models import Competition                 # noqa: E402
from src.runner import postprocess                 # noqa: E402

log = logging.getLogger("resync")


def load_state(path: str) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    comps = data.get("competitions") or {}
    values = list(comps.values()) if isinstance(comps, dict) else comps
    return [Competition.from_dict(v) for v in values]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--excel-only", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(str(ROOT / "config.json"))

    all_comps = load_state(cfg.get("data_file") or str(ROOT / "data" / "state.json"))
    log.info("state.json 读到 %d 条", len(all_comps))

    comps, dropped = postprocess(all_comps, cfg)
    log.info("后处理：保留 %d 条，拦截 %d 条", len(comps), len(dropped))

    import collections

    for field in ("platform",):
        c = collections.Counter(getattr(x, field) for x in comps)
        log.info("来源分布：%s", dict(c.most_common(12)))

    if args.dry_run:
        from src.official import categorize, prestige

        for i, c in enumerate(comps[:40], 1):
            print("%2d. %-6s %-2s %-44s | %-10s %-8s %s" % (
                i, categorize(c.title, c.organizer, c.platform),
                prestige(c.title, c.organizer, c.platform, c.rating),
                (c.title or "")[:42], c.deadline or "-",
                c.deadline_kind or "-", c.status))
        return 0

    excel_path = cfg.get("excel_file") or str(ROOT / "data" / "competitions.xlsx")
    export_excel(comps, set(), path=excel_path)
    log.info("Excel 已重写：%s", excel_path)

    if not args.excel_only:
        sheet_url = (cfg.get("feishu_sheet_url") or "").strip()
        if not sheet_url:
            log.warning("未配置 feishu_sheet_url，跳过飞书表格同步")
            return 0
        from src.feishu_sheet import sync_sheet

        sync_sheet(comps, set(), sheet_url, profile=cfg.get("lark_profile", "jingsai"))
        log.info("飞书表格已重写：%s", sheet_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
