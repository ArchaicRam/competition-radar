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

# 本机 Windows npm 全局路径；找不到时退回 PATH（Linux/CI）
_WIN_LARK_EXE = r"C:\Users\firef\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe"


def lark_exe() -> str:
    import shutil

    if os.path.exists(_WIN_LARK_EXE):
        return _WIN_LARK_EXE
    p = shutil.which("lark-cli")
    if p:
        return p
    return _WIN_LARK_EXE  # 触发 FileNotFoundError 后走 PATH 兜底


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
        except FileNotFoundError:
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
