# -*- coding: utf-8 -*-
"""飞书在线表格同步（通过 lark-cli 官方 CLI 调用）。

用法前提：
  - lark-cli 已安装，且配置了应用 profile（如 jingsai）
  - 应用已开通 sheets/drive 权限（bot 身份即可，无需用户登录）
  - 表格已创建，把 URL 填进 config.json 的 feishu_sheet_url

同步策略（每次运行全量重写，保证"今日新增"高亮干净）：
  清空 -> 写数据 -> 表头样式 -> 新增行红底 -> 列宽
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional, Set

from .models import Competition
from .official import categorize, clean_text, normalize_comp_type, prestige
from .platforms import PLATFORM_NAMES

log = logging.getLogger("feishu_sheet")

# lark-cli 的 Go 二进制：本机 Windows npm 全局路径，找不到时退回 PATH（Linux/CI）
_WIN_LARK_EXE = r"C:\Users\firef\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe"


def _lark_exe() -> str:
    import shutil

    if os.path.exists(_WIN_LARK_EXE):
        return _WIN_LARK_EXE
    p = shutil.which("lark-cli")
    if p:
        return p
    return _WIN_LARK_EXE  # 触发 FileNotFoundError 后走 PATH 兜底

_HEADERS = ["类别", "含金量", "赛名", "主办方", "类型", "开始日期", "截止日期", "阶段", "奖金", "来源", "链接"]
_COL_WIDTHS = {"A": 90, "B": 80, "C": 260, "D": 180, "E": 90, "F": 130, "G": 130, "H": 80, "I": 110, "J": 90, "K": 320}
_MAX_ROWS = 1000
_LAST_COL = "K"

# 含金量条件格式：高=红、中=橙、低=绿（整列一条规则，无需逐行样式）
_RATING_RULES = [
    ("高", "#E02020"),
    ("中", "#E67E22"),
    ("低", "#2ECC40"),
]


def sync_sheet(
    comps: List[Competition],
    new_keys: Set[str],
    sheet_url: str,
    profile: str = "jingsai",
    sheet_name: str = "Sheet1",
) -> str:
    """把比赛列表全量同步到飞书在线表格，返回表格 URL。"""
    csv_text = _build_csv(comps)
    args = ["--profile", profile, "sheets"]

    # 1. 清空旧数据（含格式，昨日的新增高亮一并清掉）
    #    注：+cells-clear 是飞书 high-risk-write，需 --yes；
    #        已获用户明确授权（仅针对本系统的竞赛总览表）。
    _lark(args + ["+cells-clear", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--range", f"A1:{_LAST_COL}{_MAX_ROWS}", "--scope", "all", "--yes"])

    # 2. 写入数据
    _lark(args + ["+csv-put", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--start-cell", "A1", "--csv", "-"], stdin_text=csv_text)

    # 3. 表头样式
    _lark(args + ["+cells-set-style", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--range", f"A1:{_LAST_COL}1", "--font-weight", "bold",
                  "--background-color", "#D9D9D9", "--horizontal-alignment", "center"])

    # 4. 今日新增行红底红字（行号 = 表头1 + 序号）
    for i, c in enumerate(comps, start=2):
        if c.key in new_keys:
            _lark(args + ["+cells-set-style", "--url", sheet_url, "--sheet-name", sheet_name,
                          "--range", f"A{i}:{_LAST_COL}{i}", "--background-color", "#FFC7CE",
                          "--font-color", "#9C0006"])

    # 5. 列宽
    _lark(args + ["+cols-resize", "--url", sheet_url, "--sheet-name", sheet_name,
                  "--widths", json.dumps(_COL_WIDTHS)])

    # 6. 含金量列颜色（条件格式，整列一条规则；已存在则不重复建）
    _ensure_rating_rules(args, sheet_url, sheet_name)
    log.info("飞书在线表格已同步: %s（%d 行，今日新增 %d）", sheet_url, len(comps), len(new_keys))
    return sheet_url


def _ensure_rating_rules(args, sheet_url, sheet_name):
    """给含金量列 B 加条件格式：高=红、中=橙、低=绿（缺哪条补哪条）。"""
    existing = set()
    try:
        resp = _lark(args + ["+cond-format-list", "--url", sheet_url, "--sheet-name", sheet_name])
        for s in (resp.get("data") or {}).get("sheets") or []:
            for r in s.get("conditional_formats") or []:
                for a in (r.get("details") or {}).get("attrs") or []:
                    if a.get("compare_type") == "containsText" and a.get("text"):
                        existing.add(a["text"])
    except Exception:  # noqa: BLE001
        pass
    for text, color in _RATING_RULES:
        if text in existing:
            continue
        style = {"fore_color": color}
        if text == "高":
            style["font"] = "bold"  # 枚举只支持 bold/italic，普通样式不传
        props = {
            "attrs": [{"compare_type": "containsText", "text": text}],
            "style": style,
        }
        _lark(args + ["+cond-format-create", "--url", sheet_url, "--sheet-name", sheet_name,
                      "--rule-type", "containsText",
                      "--ranges", json.dumps([f"B2:B{_MAX_ROWS}"]),
                      "--properties", json.dumps(props, ensure_ascii=False)])


def _build_csv(comps: List[Competition]) -> str:
    buf = io.StringIO()
    # lineterminator 用 \n：飞书 CSV 解析器会把 \r 和 \n 都当行分隔，
    # 用 CRLF 会导致隔行出现空行
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(_HEADERS)
    for c in comps:
        w.writerow([
            categorize(c.title, c.organizer, c.platform),
            prestige(c.title, c.organizer, c.platform, c.rating),
            clean_text(c.title),
            clean_text(c.organizer),
            normalize_comp_type(c.comp_type),
            c.enabled_date,
            c.deadline,
            c.status,
            c.reward,
            PLATFORM_NAMES.get(c.platform, c.platform),
            c.url,
        ])
    return buf.getvalue()


def _lark(args: List[str], stdin_text: Optional[str] = None, retries: int = 3) -> Dict:
    cmd = [_lark_exe()] + args
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=150,
                cwd=project_dir,
            )
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout or "{}")
                except json.JSONDecodeError:
                    return {"raw": proc.stdout}
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            # 网络抖动类错误重试
            if "dial tcp" in out or "transport" in out or "timed out" in out.lower():
                last_err = RuntimeError(out.strip()[-300:])
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"lark-cli 调用失败: {out.strip()[-600:]}")
        except FileNotFoundError:
            # 兜底：exe 路径失效时退回 PATH 上的 lark-cli（需 cmd 解析）
            proc = subprocess.run(
                ["lark-cli"] + args,
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=150,
                cwd=project_dir,
                shell=True,
            )
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout or "{}")
                except json.JSONDecodeError:
                    return {"raw": proc.stdout}
            raise RuntimeError(f"lark-cli 调用失败: {(proc.stderr or '')[-400:]}")
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"lark-cli 调用失败（重试后仍失败）: {last_err}")
