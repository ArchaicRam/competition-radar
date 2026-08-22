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

# 本机 Windows npm 全局路径兜底（优先走 PATH，不绑定个人目录）
_WIN_NPM_BIN = os.path.join(os.environ.get("APPDATA", ""), "npm")


def lark_exe() -> str:
    import shutil

    p = shutil.which("lark-cli")
    if p:
        return p
    # npm 全局安装的常见位置（shutil.which 已覆盖 PATHEXT，这里只做补充）
    for ext in (".cmd", ".exe", ".bat", ""):
        cand = os.path.join(_WIN_NPM_BIN, f"lark-cli{ext}")
        if ext and os.path.exists(cand):
            return cand
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
