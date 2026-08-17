# -*- coding: utf-8 -*-
"""极简 HTTP 工具：标准库 urllib 实现，零第三方依赖。"""
from __future__ import annotations

import gzip
import io
import json
import ssl
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
) -> Tuple[int, bytes, Dict[str, str]]:
    h = {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    }
    if headers:
        h.update(headers)
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
        raise HttpError(e.code, url, body) from e


def _maybe_gunzip(raw: bytes, headers: Dict[str, str]) -> bytes:
    if headers.get("Content-Encoding", "").lower() == "gzip":
        try:
            return gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            return raw
    return raw


def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> Tuple[int, bytes, Dict[str, str]]:
    return _request(url, "GET", headers=headers, timeout=timeout)


def post(
    url: str,
    data: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Tuple[int, bytes, Dict[str, str]]:
    body = data.encode("utf-8") if isinstance(data, str) else data
    return _request(url, "POST", data=body, headers=headers, timeout=timeout)


def get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30):
    status, raw, hdrs = get(url, headers=headers, timeout=timeout)
    return json.loads(raw.decode("utf-8", "ignore"))
