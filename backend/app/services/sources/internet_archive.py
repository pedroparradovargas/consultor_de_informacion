"""Conector de Internet Archive (https://archive.org).

A diferencia de OpenAlex y arXiv (que indexan *artículos* científicos), Internet
Archive contiene millones de **libros, manuales y cartillas** digitalizados, con
**PDF descargable directo** cuando son de dominio público o de acceso abierto.

Flujo:
    advancedsearch.php  ─▶ identificadores de ítems (mediatype:texts)
    metadata/{id}       ─▶ localizar el PDF libre (evitando los de préstamo/DRM)
    download/{id}/{pdf} ─▶ descarga directa
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import httpx

from app.models.schemas import FileType, ResourceItem, SearchQuery, SourceName
from app.services.sources.base import BaseSource

logger = logging.getLogger(__name__)

SEARCH_API = "https://archive.org/advancedsearch.php"
METADATA_API = "https://archive.org/metadata"
DOWNLOAD_BASE = "https://archive.org/download"
DETAILS_BASE = "https://archive.org/details"

# Mapeo de códigos ISO a las etiquetas de idioma que usa Internet Archive.
_LANG_ALIASES = {
    "es": "(spanish OR spa OR es OR español)",
    "en": "(english OR eng OR en)",
    "pt": "(portuguese OR por OR pt)",
    "fr": "(french OR fre OR fra OR fr)",
}


class InternetArchiveSource(BaseSource):
    """Busca libros y manuales descargables en Internet Archive."""

    name = SourceName.INTERNET_ARCHIVE

    async def search(self, query: SearchQuery) -> list[ResourceItem]:
        # Solo aplica cuando se piden PDFs/libros o cualquier tipo.
        if not self.matches_file_type(FileType.PDF, query.file_types):
            return []

        params = self._build_params(query)
        try:
            response = await self._client.get(SEARCH_API, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Internet Archive no disponible: %s", exc)
            return []

        try:
            docs = response.json().get("response", {}).get("docs", [])
        except ValueError:
            return []

        # Resolver el PDF descargable de cada ítem en paralelo (acotado).
        semaphore = asyncio.Semaphore(8)

        async def build(doc: dict) -> ResourceItem | None:
            async with semaphore:
                return await self._build_item(doc)

        items = await asyncio.gather(*(build(d) for d in docs))
        return [it for it in items if it is not None]

    def _build_params(self, query: SearchQuery) -> dict:
        clauses = [f"({query.query})", "mediatype:texts"]
        # Rango de años (Internet Archive entiende year:[A TO B]).
        if query.year_from is not None or query.year_to is not None:
            lo = query.year_from or 1
            hi = query.year_to or 2100
            clauses.append(f"year:[{lo} TO {hi}]")
        if query.language and query.language in _LANG_ALIASES:
            clauses.append(f"language:{_LANG_ALIASES[query.language]}")

        return {
            "q": " AND ".join(clauses),
            "fl[]": ["identifier", "title", "creator", "year", "language", "description"],
            "rows": str(min(query.limit, 40)),
            "sort[]": "downloads desc",
            "output": "json",
        }

    async def _build_item(self, doc: dict) -> ResourceItem | None:
        identifier = doc.get("identifier")
        if not identifier:
            return None

        download_url = await self._resolve_pdf(identifier)
        landing_url = f"{DETAILS_BASE}/{identifier}"

        creators = doc.get("creator")
        if isinstance(creators, str):
            authors = [creators]
        elif isinstance(creators, list):
            authors = [str(a) for a in creators]
        else:
            authors = []

        year = None
        raw_year = doc.get("year")
        if raw_year and str(raw_year)[:4].isdigit():
            year = int(str(raw_year)[:4])

        language = doc.get("language")
        if isinstance(language, list):
            language = language[0] if language else None

        description = doc.get("description")
        if isinstance(description, list):
            description = " ".join(str(d) for d in description)

        title = doc.get("title")
        if isinstance(title, list):
            title = title[0] if title else None

        return ResourceItem(
            title=title or identifier,
            authors=authors[:8],
            year=year,
            language=str(language) if language else None,
            description=(str(description)[:1000] if description else None),
            landing_url=landing_url,
            download_url=download_url,
            file_type=FileType.PDF if download_url else FileType.REPOSITORY,
            source=self.name,
            repository="Internet Archive",
            open_access=True,
            relevance=0.0,
        )

    async def _resolve_pdf(self, identifier: str) -> str | None:
        """Devuelve la URL del PDF descargable libre, o None si es de préstamo."""
        try:
            response = await self._client.get(f"{METADATA_API}/{identifier}")
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        meta = data.get("metadata", {}) or {}
        # Los ítems en préstamo (lending library) no se pueden descargar libremente.
        if str(meta.get("access-restricted-item", "")).lower() == "true":
            return None

        files = data.get("files", []) or []
        pdfs = [
            f["name"]
            for f in files
            if isinstance(f.get("name"), str)
            and f["name"].lower().endswith(".pdf")
            and not f["name"].lower().endswith("_encrypted.pdf")
        ]
        if not pdfs:
            return None
        # Preferir el PDF "principal" (suele llamarse <identifier>.pdf).
        best = next((p for p in pdfs if p.lower() == f"{identifier.lower()}.pdf"), pdfs[0])
        # El nombre del archivo puede tener espacios o acentos: codificarlo.
        return f"{DOWNLOAD_BASE}/{quote(identifier)}/{quote(best)}"
