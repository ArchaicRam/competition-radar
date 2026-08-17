# -*- coding: utf-8 -*-
"""执行器：抓取 -> 校验 -> 排序 -> 增量对比 -> 推送日报 -> 落库 -> 导出台账。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import fetchers as fetchers_mod
from . import official
from .card import build_digest_card
from .config import normalize_sources
from .csv_export import export_csv
from .excel_export import export_excel
from .fetchers.base import FetcherSkip
from .message import build_message, build_no_new_message
from .models import Competition
from .notify import FeishuNotifier
from .storage import Store

log = logging.getLogger("runner")


def run(
    config: Dict[str, Any],
    sources: Optional[List[str]] = None,
    dry_run: bool = False,
    export_csv_path: Optional[str] = None,
    log_to_console: bool = True,
) -> Dict[str, Any]:
    """执行一次完整扫描。dry_run=True 时不推送、不改状态。"""
    if log_to_console and not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)

    _apply_official_keywords(config)

    store = Store(config["data_file"])
    notifier = FeishuNotifier(
        config.get("feishu_webhook", ""),
        config.get("feishu_secret", ""),
    )
    enabled = normalize_sources(sources or config.get("sources", []))

    all_comps: List[Competition] = []
    errors: List[Dict[str, str]] = []
    for name in enabled:
        try:
            f = fetchers_mod.build(name, config)
            comps = f.fetch()
            log.info("[%s] 抓到 %d 场", name, len(comps))
            all_comps.extend(comps)
        except FetcherSkip as e:
            log.info("[%s] 跳过: %s", name, e)
        except Exception as e:  # noqa: BLE001
            errors.append({"source": name, "error": str(e)})
            log.warning("[%s] 抓取失败: %s", name, e)

    all_comps = _dedup(all_comps)

    # AI 情报员：从非接口型来源（官网公告/聚合站/揭榜挂帅页）发现比赛/需求征集
    if config.get("ai_discover"):
        try:
            from .ai_discover import discover

            discovered = discover(config.get("seed_sources") or [], config)
            if discovered:
                log.info("AI 情报员新增 %d 条（来源标注 AI发现）", len(discovered))
                all_comps.extend(discovered)
        except Exception as e:  # noqa: BLE001
            log.warning("AI 情报员失败: %s", e)

    all_comps, dropped = _sanitize(all_comps)
    for c, reason in dropped:
        log.warning("数据质量拦截: [%s] %s —— %s", c.platform, c.title, reason)

    # 排序：教育部A类优先 -> 同一主办方聚合 -> 截止日期升序
    all_comps = official.sort_competitions(all_comps)

    new, updated = store.diff(all_comps)
    log.info("共 %d 场，其中新 %d 场、更新 %d 场", len(all_comps), len(new), len(updated))

    result: Dict[str, Any] = {
        "total": len(all_comps),
        "new": len(new),
        "updated": len(updated),
        "errors": errors,
        "dropped": len(dropped),
    }

    if dry_run:
        print(_dry_run_text(new, updated, all_comps))
        return result

    bot_name = config.get("bot_name", "竞赛雷达")
    if config.get("send_table_daily", True):
        excel_path = _export_excel(config, all_comps, new)
        if excel_path:
            result["excel"] = excel_path

        # 同步飞书在线表格（可选，配了 feishu_sheet_url 才启用）
        sheet_url = config.get("feishu_sheet_url") or ""
        if sheet_url:
            try:
                from .feishu_sheet import sync_sheet

                sync_sheet(
                    all_comps,
                    {c.key for c in new},
                    sheet_url,
                    profile=config.get("lark_profile", "jingsai"),
                )
                result["sheet_url"] = sheet_url
            except Exception as e:  # noqa: BLE001
                log.warning("飞书在线表格同步失败: %s", e)

        card_excel_link = sheet_url or config.get("excel_link", "") or ""
        ai_digest_text = ""
        if config.get("ai_digest"):
            from .ai_digest import digest

            ai_digest_text = digest(new, config)
        card = build_digest_card(
            all_comps,
            {c.key for c in new},
            bot_name=bot_name,
            deadline_alert_days=int(config.get("deadline_alert_days", 7)),
            excel_link=card_excel_link,
            excel_path=excel_path or "",
            ai_digest_text=ai_digest_text,
        )
        if notifier.enabled:
            notifier.send_card(card)
            log.info("已推送情报日报卡片（%d 场，今日新增 %d）", len(all_comps), len(new))
        else:
            log.info("未配置 feishu_webhook，跳过推送（本应推送情报日报卡片）")
    else:
        message = build_message(
            new, updated,
            max_items=int(config.get("max_items_per_push", 20)),
            deadline_alert_days=int(config.get("deadline_alert_days", 7)),
            bot_name=bot_name,
        )
        if message:
            if notifier.enabled:
                notifier.send_text(message)
                log.info("已推送 %d 字消息到飞书", len(message))
            else:
                log.info("未配置 feishu_webhook，跳过推送（本应推送 %d 字）", len(message))
        elif config.get("digest_when_no_new"):
            notifier.send_text(build_no_new_message(bot_name))

    store.update(all_comps)
    if export_csv_path:
        path = export_csv(store, export_csv_path)
        log.info("CSV 台账已导出: %s", path)
        result["csv"] = path
    return result


def _export_excel(config, all_comps, new) -> Optional[str]:
    path = config.get("excel_file") or "data/competitions.xlsx"
    try:
        export_excel(all_comps, {c.key for c in new}, path=path)
        log.info("Excel 台账已导出: %s", path)
        return path
    except Exception as e:  # noqa: BLE001
        log.warning("Excel 导出失败: %s", e)
        return None


def _apply_official_keywords(config) -> None:
    kws = config.get("official_keywords")
    if isinstance(kws, list) and kws:
        official.OFFICIAL_KEYWORDS[:] = [str(k) for k in kws]


# --------------------------------------------------------------------------
# 数据质量
# --------------------------------------------------------------------------

_BAD_YEAR_PREFIX = ("1999", "1970", "0000", "1900", "2099")


def _sanitize(comps: List[Competition]) -> Tuple[List[Competition], List[Tuple[Competition, str]]]:
    ok: List[Competition] = []
    dropped: List[Tuple[Competition, str]] = []
    for c in comps:
        reason = _why_bad(c)
        if reason:
            dropped.append((c, reason))
        else:
            ok.append(c)
    return ok, dropped


def _why_bad(c: Competition) -> Optional[str]:
    title = (c.title or "").strip()
    if not title:
        return "标题为空"

    deadline = (c.deadline or "").strip()
    enabled = (c.enabled_date or "").strip()
    for s in (deadline, enabled):
        if not s:
            continue
        if s[:4] in _BAD_YEAR_PREFIX:
            return f"疑似占位日期: {s}"
        if not re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return f"日期格式异常: {s}"

    st = _parse_dt(enabled)
    dl = _parse_dt(deadline)
    if st and dl and st > dl:
        return f"开始晚于截止: {enabled} > {deadline}"
    return None


def _parse_dt(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _dedup(comps: List[Competition]) -> List[Competition]:
    seen = set()
    out = []
    for c in comps:
        if c.key in seen:
            continue
        seen.add(c.key)
        out.append(c)
    return out


def _dry_run_text(new, updated, all_comps) -> str:
    lines = [f"【DRY-RUN】共抓到 {len(all_comps)} 场，新 {len(new)} 场、更新 {len(updated)} 场", ""]
    if new:
        lines.append("新增比赛：")
        for i, c in enumerate(new[:30], 1):
            lines.append(f"{i}. {c}")
    else:
        lines.append("（本次没有新比赛）")
    if updated:
        lines.append("")
        lines.append("有更新：")
        for c in updated[:10]:
            lines.append(f"- {c}")
    return "\n".join(lines)
