# -*- coding: utf-8 -*-
"""执行器：抓取 -> 校验 -> 排序 -> 增量对比 -> 推送日报 -> 落库 -> 导出台账。"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
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

    def _fetch_one(name: str):
        try:
            f = fetchers_mod.build(name, config)
            comps = f.fetch()
            log.info("[%s] 抓到 %d 场", name, len(comps))
            return name, comps, None
        except FetcherSkip as e:
            log.info("[%s] 跳过: %s", name, e)
            return name, [], None
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] 抓取失败: %s", name, e)
            return name, [], str(e)

    if enabled:
        # 各平台互相独立，并行抓取缩短总时长；pool.map 保持 enabled 顺序
        with ThreadPoolExecutor(max_workers=min(6, len(enabled))) as pool:
            for name, comps, err in pool.map(_fetch_one, enabled):
                if err:
                    errors.append({"source": name, "error": err})
                else:
                    all_comps.extend(comps)

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

    all_comps, dropped = postprocess(all_comps, config)

    new, updated = store.diff(all_comps)
    log.info("共 %d 场，其中新 %d 场、更新 %d 场", len(all_comps), len(new), len(updated))

    # 异常检测：全部数据源失败，或总数比上一轮骤降过半 → 显式告警，避免平台改版后默默空跑
    prev_total = int(store.data.get("last_total") or 0)
    all_failed = bool(enabled) and len(errors) >= len(enabled)
    collapsed = not all_failed and prev_total >= 10 and len(all_comps) < prev_total // 2

    result: Dict[str, Any] = {
        "total": len(all_comps),
        "new": len(new),
        "updated": len(updated),
        "dropped": len(dropped),
        "errors": errors,
    }

    if dry_run:
        print(_dry_run_text(new, updated, all_comps))
        return result

    if all_failed or collapsed:
        try:
            _alert_anomaly(config, notifier, errors, len(all_comps), prev_total, collapsed)
        except Exception as e:  # noqa: BLE001
            log.warning("告警发送失败: %s", e)

    bot_name = config.get("bot_name", "竞赛雷达")
    # 推送环节的失败不应阻断状态落库，否则同样的内容会重复推送
    try:
        if all_failed and not all_comps:
            # 无任何可用数据，推日报只会误导（"共 0 场"）；告警已发，等下轮恢复
            log.warning("全部数据源失败且无数据，跳过正常日报推送")
        elif config.get("send_table_daily", True):
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
                # AI 看点只是锦上添花：失败就降级为空文本，不能拖垮整张日报卡
                try:
                    from .ai_digest import digest

                    ai_digest_text = digest(new, config)
                except Exception as e:  # noqa: BLE001
                    log.warning("AI 今日看点失败（日报照发）: %s", e)
            card = build_digest_card(
                all_comps,
                {c.key for c in new},
                bot_name=bot_name,
                deadline_alert_days=int(config.get("deadline_alert_days", 14)),
                excel_link=card_excel_link,
                excel_path=excel_path or "",
                ai_digest_text=ai_digest_text,
                site_link=(config.get("site_url") or "").strip(),
            )
            if _push_card(config, notifier, card):
                log.info("已推送情报日报卡片（%d 场，今日新增 %d）", len(all_comps), len(new))
            else:
                log.info("未配置发送通道（feishu_chat_id 或 feishu_webhook），跳过推送")
        else:
            message = build_message(
                new, updated,
                max_items=int(config.get("max_items_per_push", 20)),
                deadline_alert_days=int(config.get("deadline_alert_days", 14)),
                bot_name=bot_name,
            )
            if message:
                if _push_text(config, notifier, message):
                    log.info("已推送 %d 字消息到飞书", len(message))
                else:
                    log.info("未配置发送通道（feishu_chat_id 或 feishu_webhook），跳过推送")
            elif config.get("digest_when_no_new"):
                _push_text(config, notifier, build_no_new_message(bot_name))
    except Exception as e:  # noqa: BLE001
        log.warning("推送环节失败（状态仍会落库）: %s", e)

    store.data["last_total"] = len(all_comps)
    store.update(all_comps)
    if export_csv_path:
        path = export_csv(store, export_csv_path)
        log.info("CSV 台账已导出: %s", path)
        result["csv"] = path
    return result


def _push_card(config, notifier, card) -> bool:
    """推送卡片：应用机器人优先（feishu_chat_id），失败/未配置则降级 webhook。"""
    chat_id = (config.get("feishu_chat_id") or "").strip()
    if chat_id:
        try:
            from .feishu_app import send_card

            send_card(chat_id, card, profile=config.get("lark_profile", "jingsai"))
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("应用机器人推送失败，降级 webhook: %s", e)
    if notifier.enabled:
        notifier.send_card(card)
        return True
    return False


def _push_text(config, notifier, text) -> bool:
    """推送文本：应用机器人优先，失败/未配置则降级 webhook。"""
    chat_id = (config.get("feishu_chat_id") or "").strip()
    if chat_id:
        try:
            from .feishu_app import send_text

            send_text(chat_id, text, profile=config.get("lark_profile", "jingsai"))
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("应用机器人推送失败，降级 webhook: %s", e)
    if notifier.enabled:
        notifier.send_text(text)
        return True
    return False


def _alert_anomaly(config, notifier, errors, total, prev_total, collapsed) -> None:
    """扫描结果异常时发显式告警，区别于正常的"今日无新"。

    触发条件：全部数据源抓取失败（all_failed），
    或总数比上一轮骤降过半（collapsed，通常是平台改版/网络异常）。
    """
    bot_name = config.get("bot_name", "竞赛雷达")
    lines = [f"⚠️ {bot_name} 扫描异常，请留意", ""]
    if errors:
        lines.append(f"抓取失败的数据源（{len(errors)} 个）：")
        lines.extend(f"- {e['source']}: {e['error'][:100]}" for e in errors)
    if collapsed:
        lines.append(
            f"本轮仅 {total} 场（上一轮 {prev_total} 场，骤降过半），"
            "可能有平台改版或网络异常。"
        )
    lines.append("")
    lines.append("可在 GitHub Actions 页面查看日志，或本地 `python run_daily.py --dry-run` 排查。")
    if not _push_text(config, notifier, "\n".join(lines)):
        log.warning("告警未发送：未配置发送通道")
    else:
        log.warning("已发送扫描异常告警（errors=%d, total=%d, prev=%d）", len(errors), total, prev_total)


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
    # 外语/人文/文体类硬过滤：综合聚合站（赛氪等）和 LLM 提取都可能混入；
    # 技术平台（天池/讯飞等）不适用——它们的"翻译/词汇"多为 NLP 任务名
    if official.is_off_topic(title, platform=c.platform):
        return "与计算机主题无关"

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
    # 只按"日期"比较：截止日当天仍视为可报名（与各平台抓取器的口径一致），
    # 避免 _parse_dt 把纯日期解析成当天 00:00 导致截止日当天的比赛被误删
    if dl and dl.date() < datetime.now().date():
        return f"已截止: {deadline}"
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


def postprocess(
    comps: List[Competition],
    config: Dict[str, Any],
) -> Tuple[List[Competition], List[Tuple[Competition, str]]]:
    """共享后处理：去重 -> 数据校验 -> 官方赛事报名时间兜底 -> 排序。

    定时任务（runner.run）和手动同步（resync_sheet）都走这里，
    保证表格/卡片与真实运行行为一致。
    返回 (保留的比赛, 被数据质量拦截的 (比赛, 原因) 列表)。
    """
    comps = _dedup(comps)
    comps, dropped = _sanitize(comps)
    for c, reason in dropped:
        log.warning("数据质量拦截: [%s] %s —— %s", c.platform, c.title, reason)

    # 官方赛事报名时间兜底：有真实截止最好；否则按往届经验推断；
    # 本届报名已过或推不出窗口 → 从表中移除（不出现"待核实"）
    kept: List[Competition] = []
    for c in comps:
        if official.is_official(c.title, c.organizer) and not (c.deadline or "").strip():
            from .schedules import enrich_official

            note, keep = enrich_official(c.title, c.deadline, config)
            if not keep:
                log.warning("官方赛事无有效报名时间（本届已过或推不出窗口），移除: %s", c.title)
                continue
            if note:
                c.status = note
        kept.append(c)

    # 阶段补齐：只允许具体状态流出（用户硬性要求：绝不出现"待核实"）。
    # 有有效截止日期 → 报名中；无截止/截止不可解析 → 进行中
    today = datetime.now().date()
    for c in kept:
        c.status = official.concrete_stage(c.status, c.deadline)
    return official.sort_competitions(kept), dropped


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


