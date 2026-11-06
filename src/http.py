# -*- coding: utf-8 -*-
"""极简 HTTP 工具：标准库 urllib 实现，零第三方依赖。"""
from __future__ import annotations

import gzip
import io
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_CTX = ssl.create_default_context()
_CTX.check_hostname = True
_CTX.verify_mode = ssl.CERT_REQUIRED


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url


def _request(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 1,
) -> Tuple[int, bytes, Dict[str, str]]:
    """带瞬时错误重试的请求。

    只重试"可能恢复"的失败：网络抖动（URLError/超时/连接重置）和 5xx；
    4xx（反爬 403、参数错等）是确定性失败，重试无意义，立即抛出。
    """
    h = {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    }
    if headers:
        h.update(headers)
    last_err: Exception = RuntimeError("unreachable")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                raw = r.read()
                resp_headers = dict(r.headers)
                return r.status, _maybe_gunzip(raw, resp_headers), resp_headers
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                pass
            if e.code >= 500 and attempt < retries:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
                continue
            raise HttpError(e.code, url, body) from e
        except OSError as e:
            # URLError / 超时 / 连接重置都是 OSError 子类
            if attempt < retries:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_err


def _maybe_gunzip(raw: bytes, headers: Dict[str, str]) -> bytes:
    """按需解压 gzip 响应。

    两个坑都踩过，必须同时防：
      1. **响应头大小写不固定**。`dict(r.headers)` 保留服务端原始大小写，
         DeepSeek 官方 API 发的是小写 `content-encoding: gzip`，
         原来的 `headers.get("Content-Encoding")` 取不到 → 拿到一坨压缩字节 →
         `json.loads` 报 "Expecting value: line 1 column 1 (char 0)"，极难定位。
      2. **有的服务端不声明却压缩**，所以再用 gzip 魔数 1f 8b 兜一层底。
    """
    enc = ""
    for k, v in (headers or {}).items():
        if k.lower() == "content-encoding":
            enc = str(v).lower()
            break
    if "gzip" in enc or raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            return raw
    return raw


def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30, retries: int = 1) -> Tuple[int, bytes, Dict[str, str]]:
    return _request(url, "GET", headers=headers, timeout=timeout, retries=retries)


def post(
    url: str,
    data: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 0,
) -> Tuple[int, bytes, Dict[str, str]]:
    """POST 默认不自动重试（避免 webhook 等非幂等请求重复发送），需要时显式传 retries。"""
    body = data.encode("utf-8") if isinstance(data, str) else data
    return _request(url, "POST", data=body, headers=headers, timeout=timeout, retries=retries)


def get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30, retries: int = 1):
    status, raw, hdrs = get(url, headers=headers, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8", "ignore"))
