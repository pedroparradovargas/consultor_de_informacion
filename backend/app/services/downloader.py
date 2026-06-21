"""Descargador asíncrono y responsable de PDFs de repositorios abiertos.

Características de "scraping responsable a escala":
- Concurrencia global limitada (semáforo).
- Rate limiting por dominio (espera mínima entre peticiones al mismo host).
- Respeto de robots.txt.
- Protección SSRF validando cada salto de redirección.
- Validación de tipo de contenido (solo PDF) y tamaño máximo.
- Reintentos con backoff exponencial ante errores transitorios.
- Deduplicación: no vuelve a descargar un archivo ya presente.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from app.config import Settings, get_settings
from app.core.net_safety import UnsafeUrlError, assert_safe_url
from app.core.robots import RobotsCache
from app.models.schemas import DownloadResultItem, DownloadStatus

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF-"
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class DomainRateLimiter:
    """Garantiza una espera mínima entre peticiones al mismo host."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            elapsed = now - self._last.get(host, 0.0)
            if elapsed < self._delay:
                await asyncio.sleep(self._delay - elapsed)
            self._last[host] = time.monotonic()


class Downloader:
    """Gestiona la descarga concurrente y segura de un conjunto de URLs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._robots = RobotsCache(self._settings.http_user_agent)
        self._rate = DomainRateLimiter(self._settings.per_domain_delay_seconds)
        self._semaphore = asyncio.Semaphore(self._settings.download_concurrency)
        self._max_bytes = self._settings.max_download_mb * 1024 * 1024

    async def download_many(self, urls: list[str]) -> list[DownloadResultItem]:
        dest = Path(self._settings.download_dir)
        dest.mkdir(parents=True, exist_ok=True)

        timeout = httpx.Timeout(self._settings.http_timeout_seconds, read=60.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": self._settings.http_user_agent},
            follow_redirects=False,  # validamos cada salto manualmente (anti-SSRF)
        ) as client:
            tasks = [self._download_one(client, url, dest) for url in urls]
            return await asyncio.gather(*tasks)

    async def _download_one(
        self, client: httpx.AsyncClient, url: str, dest: Path
    ) -> DownloadResultItem:
        async with self._semaphore:
            try:
                final_url, response = await self._fetch_with_redirects(client, url)
            except UnsafeUrlError as exc:
                return self._result(url, DownloadStatus.BLOCKED, reason=str(exc))
            except httpx.HTTPError as exc:
                return self._result(url, DownloadStatus.FAILED, reason=str(exc))

            if response is None:
                return self._result(
                    url, DownloadStatus.BLOCKED, reason="Bloqueado por robots.txt."
                )

            try:
                return await self._save(url, final_url, response, dest)
            finally:
                await response.aclose()

    async def _fetch_with_redirects(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str, httpx.Response | None]:
        """Sigue redirecciones validando cada salto (robots + SSRF + rate limit)."""
        current = url
        for _ in range(self._settings.http_max_redirects + 1):
            await assert_safe_url(current)
            if self._settings.respect_robots and not await self._robots.allowed(
                client, current
            ):
                return current, None

            host = urlparse(current).netloc
            await self._rate.wait(host)

            response = await self._request_with_retries(client, current)
            if response.is_redirect and "location" in response.headers:
                location = str(response.headers["location"])
                await response.aclose()
                current = httpx.URL(current).join(location).human_repr()
                continue
            return current, response
        raise httpx.HTTPError("Demasiadas redirecciones.")

    async def _request_with_retries(
        self, client: httpx.AsyncClient, url: str
    ) -> httpx.Response:
        """GET en streaming con reintentos y backoff exponencial."""
        last_exc: Exception | None = None
        for attempt in range(self._settings.download_retries):
            try:
                request = client.build_request("GET", url)
                response = await client.send(request, stream=True)
                if response.status_code >= 500:
                    await response.aclose()
                    raise httpx.HTTPError(f"HTTP {response.status_code}")
                return response
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s...
        raise last_exc or httpx.HTTPError("Fallo de descarga.")

    async def _save(
        self,
        original_url: str,
        final_url: str,
        response: httpx.Response,
        dest: Path,
    ) -> DownloadResultItem:
        if response.status_code != 200:
            return self._result(
                original_url,
                DownloadStatus.FAILED,
                reason=f"HTTP {response.status_code}",
            )

        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" not in content_type and not final_url.lower().endswith(
            ".pdf"
        ):
            return self._result(
                original_url,
                DownloadStatus.SKIPPED,
                reason=f"No es PDF (content-type: {content_type or 'desconocido'}).",
            )

        target = dest / self._filename_for(final_url)
        if target.exists():
            return self._result(
                original_url,
                DownloadStatus.SKIPPED,
                reason="Ya descargado.",
                path=str(target),
                size_bytes=target.stat().st_size,
            )

        total = 0
        first_chunk = True
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with tmp.open("wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if first_chunk:
                        if not chunk.startswith(_PDF_MAGIC):
                            tmp.unlink(missing_ok=True)
                            return self._result(
                                original_url,
                                DownloadStatus.SKIPPED,
                                reason="El contenido no es un PDF válido.",
                            )
                        first_chunk = False
                    total += len(chunk)
                    if total > self._max_bytes:
                        tmp.unlink(missing_ok=True)
                        return self._result(
                            original_url,
                            DownloadStatus.SKIPPED,
                            reason=f"Supera el límite de {self._settings.max_download_mb} MB.",
                        )
                    fh.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            return self._result(original_url, DownloadStatus.FAILED, reason=str(exc))

        tmp.rename(target)
        return self._result(
            original_url,
            DownloadStatus.DOWNLOADED,
            path=str(target),
            size_bytes=total,
        )

    def _filename_for(self, url: str) -> str:
        """Nombre de archivo seguro y determinista a partir de la URL."""
        path = unquote(urlparse(url).path)
        name = Path(path).name or "documento"
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        name = _FILENAME_SAFE.sub("_", name).strip("_")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return f"{digest}_{name}"

    @staticmethod
    def _result(
        url: str,
        status: DownloadStatus,
        *,
        reason: str | None = None,
        path: str | None = None,
        size_bytes: int | None = None,
    ) -> DownloadResultItem:
        return DownloadResultItem(
            url=url, status=status, reason=reason, path=path, size_bytes=size_bytes
        )
