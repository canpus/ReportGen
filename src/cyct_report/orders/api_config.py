"""Portable, user-owned visual service settings; credentials are never returned in errors."""

import base64
import ctypes
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.parse import urlsplit, urlunsplit


def local_address(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def lan_host(host):
    networks = [
        ipaddress.ip_network(n)
        for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
    ]
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(x[4][0])
                for x in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            ]
        except OSError:
            return False
    return bool(addresses) and all(
        ip.is_loopback or any(ip in n for n in networks) for ip in addresses
    )


def endpoint(value):
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError("请填写有效的 API 地址和端口。")
    raw = urlsplit(value if "://" in value else "//" + value)
    if not raw.hostname or raw.username or raw.password or raw.query or raw.fragment:
        raise ValueError("API 地址应只包含主机、端口和服务路径。")
    if raw.port is not None and not 1 <= raw.port <= 65535:
        raise ValueError("无效的 API 端口。")
    scheme = raw.scheme or (
        "http" if local_address(raw.hostname) or lan_host(raw.hostname) else "https"
    )
    if (
        scheme not in ("http", "https")
        or scheme == "http"
        and not (local_address(raw.hostname) or lan_host(raw.hostname))
    ):
        raise ValueError("公网模型地址需要 HTTPS；公司内网地址可使用 HTTP。")
    path = raw.path.rstrip("/") or "/v1"
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return urlunsplit((scheme, raw.netloc, path, "", ""))


def authorization(options):
    field = options.get("auth_header", "Authorization").strip() or "Authorization"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", field) or field.lower() in {
        "host",
        "content-length",
        "content-type",
        "connection",
        "proxy-authorization",
    }:
        raise ValueError("无效的认证头名称。")
    key = (
        options["api_key"]
        if "api_key" in options
        else os.getenv(options.get("api_key_env", "ORDER_VISION_KEY"), "")
    )
    prefix = options.get("auth_prefix", "Bearer").strip()
    if any(c in (key + prefix) for c in "\r\n"):
        raise ValueError("认证信息不可包含换行。")
    return {field: " ".join(filter(None, (prefix, key)))} if key else {}


def _dpapi(data, protect):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]

    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    dest = Blob()
    fn = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dest)):
        raise ValueError("当前 Windows 用户无法访问此密钥，请重新输入。")
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(dest.data))


def load_settings(path):
    path = Path(path)
    if not path.exists():
        return {}
    settings = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("无效的配置文件。")
    protected = settings.pop("windows_key", None)
    if protected and os.name == "nt":
        try:
            settings["api_key"] = _dpapi(base64.b64decode(protected), False).decode()
        except ValueError:
            settings["api_key"] = ""
    return settings


def save_settings(path, settings):
    settings = dict(settings)
    if settings.get("enabled") or settings.get("base_url"):
        endpoint(settings.get("base_url", ""))
        if not settings.get("model", "").strip():
            raise ValueError("请填写模型名称。")
        authorization(settings)
    if os.name == "nt" and settings.get("api_key"):
        settings["windows_key"] = base64.b64encode(
            _dpapi(settings.pop("api_key").encode(), True)
        ).decode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as tmp:
        filename = Path(tmp.name)
        try:
            json.dump(settings, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(filename, path)
        finally:
            filename.unlink(missing_ok=True)


def desktop_config(settings):
    return {
        "ocr_parser": {"provider": "none"},
        "llm_extractor": dict(settings, provider="openai")
        if settings.get("enabled")
        else {"provider": "rules"},
        "allow_external_pages": bool(settings.get("allow_external_pages")),
    }
