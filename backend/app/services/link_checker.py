"""Verificación de enlaces para descartar páginas muertas o en mantenimiento.

Antes de devolver los resultados de una búsqueda, comprobamos que el recurso
siga existiendo. Así el usuario no recibe páginas que dan **404 (no encontrado)**,
**410 (eliminado)** o **5xx (servidor caído / en mantenimiento)**.

Criterio (deliberadamente conservador para no descartar de más):

- Se considera **muerto** sólo ante señales inequívocas: 404, 410, 451 o
  cualquier 5xx (incluido 503 «Service Unavailable» = mantenimiento).
- Se considera **vivo** todo lo demás (2xx, 3xx, 401, 403, 429…). Un 403 puede
  ser una restricción del «polite pool» o anti-bot, no que el recurso no exista.
- Ante un **error de red / timeout** se conserva el recurso (no penalizamos por
  un fallo transitorio ni por una política de red que bloquee la comprobación).

La verificación respeta la protección anti-SSRF y usa HEAD (con respaldo a un
GET ligero si el servidor no admite HEAD), con concurrencia y timeout acotados.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings
from app.core.net_safety import UnsafeUrlError, assert_safe_url
from app.models.schemas import ResourceItem

logger = logging.getLogger(__name__)

# Códigos que indican que el recurso ya no está disponible.
_DEAD_STATUS = {404, 410, 451}


class LinkChecker:
    """Comprueba la disponibilidad de los enlaces de un conjunto de recursos."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._concurrency = 16
        self._timeout = httpx.Timeout(8.0, connect=5.0)

    @staticmethod
    def _url_of(item: ResourceItem) -> str | None:
        """URL representativa a verificar (preferimos la de descarga)."""
        return item.download_url or item.landing_url

    async def filter_alive(
        self, items: list[ResourceItem]
    ) -> tuple[list[ResourceItem], int]:
        """Devuelve (recursos vivos, nº de recursos descartados por estar muertos)."""
        if not items:
            return items, 0

        semaphore = asyncio.Semaphore(self._concurrency)
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": self._settings.http_user_agent},
            follow_redirects=True,
            max_redirects=self._settings.http_max_redirects,
        ) as client:

            async def check(item: ResourceItem) -> bool:
                async with semaphore:
                    return await self._is_alive(client, item)

            verdicts = await asyncio.gather(*(check(it) for it in items))

        alive = [it for it, ok in zip(items, verdicts, strict=True) if ok]
        removed = len(items) - len(alive)
        return alive, removed

    async def _is_alive(self, client: httpx.AsyncClient, item: ResourceItem) -> bool:
        url = self._url_of(item)
        if not url:
            # Sin enlace que comprobar: no podemos afirmar que esté muerto.
            return True

        try:
            await assert_safe_url(url)
        except UnsafeUrlError:
            # Host no resoluble o no público → no es un recurso útil/seguro.
            return False

        try:
            response = await client.head(url)
            # Algunos servidores no admiten HEAD: reintentamos con un GET ligero.
            if response.status_code in (405, 501):
                response = await self._light_get(client, url)
        except httpx.HTTPError as exc:
            logger.debug("No se pudo verificar %s (%s): se conserva.", url, exc)
            return True  # fallo transitorio / red bloqueada → conservar

        if response.status_code in _DEAD_STATUS or response.status_code >= 500:
            host = urlparse(url).netloc
            logger.info(
                "Descartado recurso muerto (HTTP %s) en %s: %s",
                response.status_code,
                host,
                item.title[:80],
            )
            return False
        return True

    async def _light_get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET que sólo pide el primer byte para confirmar disponibilidad."""
        return await client.get(url, headers={"Range": "bytes=0-0"})
