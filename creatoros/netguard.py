"""Network guard: the Explorer only ever fetches PUBLIC internet addresses.

Offers are attacker-controlled input, and they contain URLs. Without this guard a hostile offer could make
the crawler read http://127.0.0.1:.../api/..., a router admin page, or a cloud metadata endpoint (SSRF).
Checked on the first request AND on every redirect / sub-request.
"""
import ipaddress
import socket
from functools import lru_cache
from typing import Tuple
from urllib.parse import urlparse

_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")


@lru_cache(maxsize=512)
def _host_is_public(host: str) -> Tuple[bool, str]:
    h = (host or "").strip("[]").lower().rstrip(".")
    if not h:
        return False, "no host"
    if h == "localhost" or h.endswith(_BLOCKED_SUFFIXES):
        return False, "local hostname"
    try:
        ips = [ipaddress.ip_address(h)]
    except ValueError:
        try:
            ips = [ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(h, None)]
        except (socket.gaierror, UnicodeError):
            return False, "host does not resolve"
    for ip in ips:
        if not ip.is_global:
            return False, f"non-public address {ip}"
    return True, ""


def is_public_url(url: str) -> Tuple[bool, str]:
    """(True, '') if `url` is http(s) to a public address, else (False, reason)."""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https"):
        return False, f"scheme '{p.scheme}' not allowed"
    if p.username or p.password:
        return False, "credentials in URL"
    return _host_is_public(p.hostname or "")
