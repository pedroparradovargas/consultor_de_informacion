"""Utilidades de seguridad: limitador de tasa y cliente HTTP seguro.

- Rate limiting en memoria (suficiente para una sola instancia; en producción
  con múltiples réplicas conviene usar Redis).
- Cliente HTTP con timeouts, límite de redirecciones y User-Agent honesto para
  evitar abusos y mitigar SSRF / cuelgues.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

import httpx
from fastapi import HTTPException, Request, status

from app.config import Settings, get_settings


class RateLimiter:
    """Limitador de tasa por IP usando ventana deslizante en memoria."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_id: str) -> None:
        """Registra una petición y lanza HTTP 429 si se supera el límite."""
        now = time.monotonic()
        window_start = now - self._window
        hits = self._hits[client_id]

        # Descartar marcas de tiempo fuera de la ventana.
        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self._max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas peticiones. Inténtalo de nuevo más tarde.",
            )
        hits.append(now)


_settings = get_settings()
_rate_limiter = RateLimiter(
    max_requests=_settings.rate_limit_requests,
    window_seconds=_settings.rate_limit_window_seconds,
)


def rate_limit(request: Request) -> None:
    """Dependencia de FastAPI que aplica el límite de tasa por IP."""
    client_ip = request.client.host if request.client else "unknown"
    _rate_limiter.check(client_ip)


def build_http_client(settings: Settings | None = None) -> httpx.AsyncClient:
    """Crea un cliente HTTP asíncrono con valores seguros por defecto."""
    settings = settings or get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
        max_redirects=settings.http_max_redirects,
    )
