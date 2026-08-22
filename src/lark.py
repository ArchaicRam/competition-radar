# -*- coding: utf-8 -*-
"""lark-cli 统一调用（在线表格同步 / 应用机器人发消息共用）。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("lark")

# Windows npm 全局安装的候选位置（优先走 PATH，找不到再逐个探测，不绑定用户名）
_NPM_BIN = os.path.join(os.environ.get("APPDATA", ""), "npm")
_LARK_CANDIDATES = [
    os.path.join(_NPM_BIN, "node_modules", "@larksuite", "cli", "bin", "lark-cli.exe"),
    os.path.join(_NPM_BIN, "lark-cli.cmd"),
    os.path.join(_NPM_BIN, "lark-cli.exe"),
]


def lark_exe() -> str:
    """定位 lark-cli。

    Windows 上优先直连 node_modules 里的 .exe：npm 的 .cmd/.ps1 垫片会经
    cmd.exe 重新解析参数，卡片 JSON 里的引号/特殊字符会被搅坏；
    PATH 兜底主要服务 Linux/CI。
    """
    for cand in _LARK_CANDIDATES:
        if cand and os.path.exists(cand):
            return cand
    import shutil

    p = shutil.which("lark-cli")
    if p:
        return p
    return "lark-cli"  # 最后交给 PATH；仍找不到会抛 FileNotFoundError


def lark(args: List[str], stdin_text: Optional[str] = None, retries: int = 3) -> Dict[str, Any]:
    """调用 lark-cli，带网络抖动重试。"""
    cmd = [lark_exe()] + args
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
                errors="replace",  # Windows 命令行报错可能是 GBK，避免读线程解码崩溃
                timeout=150,
                cwd=project_dir,
            )
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout or "{}")
                except json.JSONDecodeError:
                    return {"raw": proc.stdout}
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if "dial tcp" in out or "transport" in out or "timed out" in out.lower():
                last_err = RuntimeError(out.strip()[-300:])
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"lark-cli 调用失败: {out.strip()[-600:]}")
        except FileNotFoundError as e:
            # 绝不退回 shell=True：参数来自抓取/LLM 内容，经 cmd.exe 会被注入
            raise RuntimeError(f"找不到 lark-cli 可执行文件（cmd={[lark_exe()] + args[:1]}）") from e
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"lark-cli 调用失败（重试后仍失败）: {last_err}")
