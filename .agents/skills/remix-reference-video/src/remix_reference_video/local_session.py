"""Single-use localhost session nonces for privileged workbench actions."""

from __future__ import annotations

import ipaddress
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlsplit


class LocalSessionError(ValueError):
    pass


@dataclass
class _Session:
    nonce: str
    expires_at: float


class LocalSessionStore:
    def __init__(self, *, ttl_seconds: float = 900.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, _Session] = {}
        self._lock = Lock()

    def issue(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = _Session(nonce=nonce, expires_at=time.monotonic() + self.ttl_seconds)
        return session_id, nonce

    def rotate(
        self,
        *,
        peer_host: str | None,
        host: str | None,
        origin: str | None,
        scheme: str,
        session_id: str | None,
        nonce: str | None,
    ) -> str:
        if not self._is_loopback(peer_host):
            raise LocalSessionError("request peer must be loopback")
        if not self._valid_host(host):
            raise LocalSessionError("request Host is not allowed")
        expected_origin = f"{scheme}://{host}"
        if origin != expected_origin:
            raise LocalSessionError("request Origin does not match Host")
        if not session_id or not nonce:
            raise LocalSessionError("local session cookie and nonce are required")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.expires_at < time.monotonic():
                self._sessions.pop(session_id, None)
                raise LocalSessionError("local session is missing or expired")
            if not secrets.compare_digest(session.nonce, nonce):
                raise LocalSessionError("local session nonce is invalid or already used")
            next_nonce = secrets.token_urlsafe(32)
            session.nonce = next_nonce
            session.expires_at = time.monotonic() + self.ttl_seconds
            return next_nonce

    @staticmethod
    def _is_loopback(value: str | None) -> bool:
        if not value:
            return False
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return value == "localhost"

    @staticmethod
    def _valid_host(value: str | None) -> bool:
        if not value or any(character in value for character in ("/", "\\", "@", " ")):
            return False
        parsed = urlsplit("//" + value)
        hostname = parsed.hostname
        if hostname == "localhost":
            return True
        try:
            return hostname is not None and ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False


__all__ = ["LocalSessionError", "LocalSessionStore"]
