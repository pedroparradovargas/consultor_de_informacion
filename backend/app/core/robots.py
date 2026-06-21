"""Verificación de robots.txt con caché en memoria.

Scraping responsable: antes de descargar de un host, comprobamos que su
robots.txt no lo prohíba para nuestro User-Agent. El resultado se cachea por
host durante un tiempo para no pedir robots.txt en cada descarga.
"""

from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


class RobotsCache:
    """Caché de parsers de robots.txt por host con expiración (TTL)."""

    def __init__(self, user_agent: str, ttl_seconds: int = 3600) -> None:
        self._user_agent = user_agent
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, RobotFileParser]] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """Indica si nuestro User-Agent puede descargar la URL."""
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        parser = await self._get_parser(client, host_key)
        if parser is None:
            # Si no hay robots.txt o no se pudo leer, se asume permitido.
            return True
        return parser.can_fetch(self._user_agent, url)

    async def _get_parser(
        self, client: httpx.AsyncClient, host_key: str
    ) -> RobotFileParser | None:
        cached = self._cache.get(host_key)
        now = time.monotonic()
        if cached and now - cached[0] < self._ttl:
            return cached[1]

        robots_url = urljoin(host_key + "/", "robots.txt")
        parser = RobotFileParser()
        try:
            response = await client.get(robots_url)
            if response.status_code >= 400:
                # Sin robots.txt accesible → permitir.
                self._cache[host_key] = (now, _allow_all_parser())
                return self._cache[host_key][1]
            parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser = _allow_all_parser()
        self._cache[host_key] = (now, parser)
        return parser


def _allow_all_parser() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse([])  # sin reglas → todo permitido
    return parser
