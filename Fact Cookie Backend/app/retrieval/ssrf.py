"""SSRF protection for direct HTTP fetches."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.errors import AppError


class SSRFError(AppError):
    status_code = 400
    code = "ssrf_blocked"


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SSRFError("Only http and https URLs are allowed.")
    if not parsed.hostname:
        raise SSRFError("URL must include a hostname.")
    try:
        infos = await __import__("asyncio").get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SSRFError("Could not resolve hostname.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked_ip(ip):
            raise SSRFError("URL resolves to a blocked address.")
    return url


async def validate_redirect_chain(urls: list[str]) -> list[str]:
    validated = []
    for url in urls:
        validated.append(await validate_url(url))
    return validated
