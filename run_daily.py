#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛情报每日扫描入口。

用法：
  python run_daily.py                  # 抓取 -> 飞书推送 -> 落库
  python run_daily.py --dry-run        # 只打印结果，不推送、不改状态
  python run_daily.py --test-notify    # 向飞书发一条测试消息
  python run_daily.py --reset          # 清空"已见"记录（下次全部算新比赛）
  python run_daily.py --sources tianchi,datafountain   # 只抓指定平台
  python run_daily.py --export-csv     # 同时导出 CSV 台账 data/competitions.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import load_config
from src.notify import FeishuNotifier
from src.runner import run


def main():
    ap = argparse.ArgumentParser(description="竞赛情报监控（大学生计算机竞赛聚合）")
    ap.add_argument("--dry-run", action="store_true", help="只抓取并打印，不推送、不改状态")
    ap.add_argument("--test-notify", action="store_true", help="向飞书发送一条测试消息")
    ap.add_argument("--demo", action="store_true", help="发送一张演示卡片（含红色高亮示例）")
    ap.add_argument("--reset", action="store_true", help="清空已见记录（下次全部视为新比赛）")
    ap.add_argument("--sources", default="", help="本次只抓指定平台，逗号分隔，如 tianchi,datafountain")
    ap.add_argument("--config", default="config.json", help="配置文件路径（默认 config.json）")
    ap.add_argument("--export-csv", action="store_true", help="同时导出 CSV 台账 data/competitions.csv")
    args = ap.parse_args()

    config = load_config(args.config)

    if args.test_notify:
        chat_id = (config.get("feishu_chat_id") or "").strip()
        msg = f"✅ {config.get('bot_name', '赛探')}已接通！\n以后每天扫描到新比赛会自动推送到本群。\n（这是一条测试消息）"
        if chat_id:
            from src.feishu_app import send_text

            send_text(chat_id, msg, profile=config.get("lark_profile", "jingsai"))
            print("已通过应用机器人发送测试消息，请到飞书群查看。")
            return
        notifier = FeishuNotifier(
            config.get("feishu_webhook", ""),
            config.get("feishu_secret", ""),
        )
        if not notifier.enabled:
            print("config.json 里还没有配置 feishu_chat_id 或 feishu_webhook，无法发送测试消息。")
            sys.exit(1)
        notifier.send_text(msg)
        print("测试消息已发送，请到飞书群查看。")
        return

    if args.demo:
        from src.card import build_digest_card
        from src.models import Competition

        notifier = FeishuNotifier(
            config.get("feishu_webhook", ""),
            config.get("feishu_secret", ""),
        )
        if not notifier.enabled:
            print("config.json 里还没有配置 feishu_webhook，无法发送演示卡片。")
            sys.exit(1)
        demo_new = {"demo:1", "demo:2"}
        demo_comps = [
            Competition(
                key="demo:1", title="示例·某某企业AI挑战赛（今日新增）", platform="tianchi",
                organizer="某科技公司", url="https://example.com/1", deadline="2026-08-20",
                reward="¥100,000", comp_type="AI", status="报名中",
                enabled_date="2026-08-10",
            ),
            Competition(
                key="demo:2", title="示例·蓝桥杯全国软件大赛（官方A类·今日新增）", platform="datafountain",
                organizer="工业和信息化部人才交流中心", url="https://example.com/2", deadline="2026-08-25",
                reward="", comp_type="综合", status="报名中",
            ),
            Competition(
                key="demo:3", title="示例·某老牌算法赛（无高亮）", platform="nowcoder",
                organizer="牛客", url="https://example.com/3", deadline="2026-09-10",
                reward="", comp_type="算法竞赛", status="进行中",
                enabled_date="2026-07-01",
            ),
            Competition(
                key="demo:4", title="示例·即将截止的比赛", platform="xfyun",
                organizer="某企业", url="https://example.com/4", deadline="2026-08-17",
                reward="¥10万", comp_type="AI", status="报名中",
            ),
        ]
        card = build_digest_card(
            demo_comps, demo_new,
            bot_name=config.get("bot_name", "赛探"),
            deadline_alert_days=int(config.get("deadline_alert_days", 14)),
            excel_link=config.get("excel_link", "") or "",
            excel_path="data/competitions.xlsx",
        )
        notifier.send_card(card)
        print("演示卡片已发送（红色=今日新增，含官方A类与即将截止示例），请到飞书群查看。")
        return

    if args.reset:
        if args.dry_run:
            # --dry-run 承诺"不改状态"，reset 优先级服从它
            print("--dry-run 模式下忽略 --reset（不修改状态）。")
        else:
            from src.storage import Store
            Store(config["data_file"]).reset()
            print("已清空已见记录。")

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    result = run(
        config,
        sources=sources,
        dry_run=args.dry_run,
        export_csv_path="data/competitions.csv" if args.export_csv else None,
    )
    print(f"\n完成：共 {result['total']} 场，新 {result['new']} 场，更新 {result['updated']} 场")
    if result.get("excel"):
        print(f"Excel 台账: {result['excel']}")
    if result["errors"]:
        print("部分平台抓取失败：")
        for e in result["errors"]:
            print(f"  - {e['source']}: {e['error']}")
    if result.get("dropped"):
        print(f"数据质量拦截：{result['dropped']} 条（详见日志）")


if __name__ == "__main__":
    main()
