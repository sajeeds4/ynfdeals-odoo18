from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse


class SSRFValidationError(ValueError):
    pass


def _normalize_hostname(hostname: str) -> str:
    host = str(hostname or "").strip().rstrip(".").lower()
    if not host:
        raise SSRFValidationError("missing_hostname")
    try:
        return host.encode("idna").decode("ascii")
    except Exception as exc:
        raise SSRFValidationError("invalid_hostname") from exc


def _domain_allowed(hostname: str, allowed_domains: tuple[str, ...] | None) -> bool:
    if not allowed_domains:
        return True
    host = _normalize_hostname(hostname)
    for domain in allowed_domains:
        allowed = _normalize_hostname(domain)
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def _reject_private_address(raw_address: str) -> None:
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError:
        return
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise SSRFValidationError("private_address_blocked")


def _resolve_public_addresses(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFValidationError("hostname_resolution_failed") from exc
    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        raise SSRFValidationError("hostname_resolution_failed")
    for address in addresses:
        _reject_private_address(address)


def validate_public_http_url(
    value: str,
    *,
    allowed_domains: tuple[str, ...] | None = None,
    require_dns: bool = True,
) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise SSRFValidationError("missing_url")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise SSRFValidationError("unsupported_url_scheme")
    if parsed.username or parsed.password:
        raise SSRFValidationError("url_credentials_forbidden")
    if not parsed.hostname:
        raise SSRFValidationError("missing_hostname")
    hostname = _normalize_hostname(parsed.hostname)
    if not _domain_allowed(hostname, allowed_domains):
        raise SSRFValidationError("host_not_allowed")
    _reject_private_address(hostname)
    if require_dns:
        _resolve_public_addresses(hostname)
    normalized_netloc = hostname
    if parsed.port:
        if parsed.port not in {80, 443}:
            raise SSRFValidationError("url_port_forbidden")
        normalized_netloc = f"{hostname}:{parsed.port}"
    return urlunparse((parsed.scheme, normalized_netloc, parsed.path or "/", "", parsed.query, ""))
