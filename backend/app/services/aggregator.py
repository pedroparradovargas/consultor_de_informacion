"""Agregador de fuentes.

Orquesta la consulta concurrente a todas las fuentes seleccionadas, deduplica
y ordena los resultados por relevancia. Es el único punto que la capa de API
necesita conocer.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.security import build_http_client
from app.models.schemas import ResourceItem, SearchQuery, SourceName
from app.services.link_checker import LinkChecker
from app.services.sources.arxiv import ArxivSource
from app.services.sources.base import BaseSource
from app.services.sources.internet_archive import InternetArchiveSource
from app.services.sources.openalex import OpenAlexSource

logger = logging.getLogger(__name__)

# Registro de fuentes disponibles. Para añadir una nueva, basta con registrarla
# aquí; el resto del sistema la descubre automáticamente.
SOURCE_REGISTRY: dict[SourceName, type[BaseSource]] = {
    SourceName.OPENALEX: OpenAlexSource,
    SourceName.ARXIV: ArxivSource,
    SourceName.INTERNET_ARCHIVE: InternetArchiveSource,
}


class SearchAggregator:
    """Ejecuta búsquedas en paralelo sobre múltiples fuentes."""

    def __init__(self) -> None:
        self._link_checker = LinkChecker()

    async def run(self, query: SearchQuery) -> tuple[list[ResourceItem], list[str]]:
        """Devuelve (resultados ordenados, advertencias)."""
        warnings: list[str] = []
        async with build_http_client() as client:
            sources = [
                SOURCE_REGISTRY[name](client)
                for name in query.sources
                if name in SOURCE_REGISTRY
            ]
            tasks = [source.search(query) for source in sources]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        collected: list[ResourceItem] = []
        for source, outcome in zip(sources, outcomes, strict=True):
            if isinstance(outcome, Exception):
                logger.exception("Fallo en la fuente %s", source.name, exc_info=outcome)
                warnings.append(f"La fuente '{source.name.value}' falló y se omitió.")
                continue
            collected.extend(outcome)

        deduped = self._deduplicate(collected)
        ranked = self._rank(deduped)
        top = ranked[: query.limit]

        if query.verify_links and top:
            top, removed = await self._link_checker.filter_alive(top)
            if removed:
                warnings.append(
                    f"Se descartaron {removed} recurso(s) con enlaces caídos "
                    f"(404/410) o en mantenimiento."
                )

        return top, warnings

    @staticmethod
    def _deduplicate(items: list[ResourceItem]) -> list[ResourceItem]:
        """Elimina duplicados por título normalizado, conservando el mejor."""
        seen: dict[str, ResourceItem] = {}
        for item in items:
            key = " ".join(item.title.lower().split())
            existing = seen.get(key)
            if existing is None:
                seen[key] = item
            elif item.download_url and not existing.download_url:
                # Preferir el que sí tiene enlace de descarga.
                seen[key] = item
        return list(seen.values())

    @staticmethod
    def _rank(items: list[ResourceItem]) -> list[ResourceItem]:
        """Ordena por (tiene descarga, acceso abierto, relevancia, año)."""
        return sorted(
            items,
            key=lambda r: (
                r.download_url is not None,
                r.open_access,
                r.relevance,
                r.year or 0,
            ),
            reverse=True,
        )
