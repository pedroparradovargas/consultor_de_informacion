"""Conector de OpenAlex (https://openalex.org).

OpenAlex es un catálogo abierto y gratuito de trabajos académicos. No requiere
clave de API. Indicar un correo de contacto activa el "polite pool" (mejor
rendimiento) y es una buena práctica de ciudadanía de la red.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.models.schemas import FileType, ResourceItem, SearchQuery, SourceName
from app.services.sources.base import BaseSource

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org/works"


class OpenAlexSource(BaseSource):
    """Busca trabajos académicos abiertos en OpenAlex."""

    name = SourceName.OPENALEX

    async def search(self, query: SearchQuery) -> list[ResourceItem]:
        params = self._build_params(query)
        try:
            response = await self._client.get(OPENALEX_API, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("OpenAlex no disponible: %s", exc)
            return []

        payload = response.json()
        results: list[ResourceItem] = []
        for work in payload.get("results", []):
            item = self._parse_work(work, query)
            if item is not None:
                results.append(item)
        return results

    def _build_params(self, query: SearchQuery) -> dict[str, str]:
        filters: list[str] = []
        if query.year_from is not None:
            filters.append(f"from_publication_date:{query.year_from}-01-01")
        if query.year_to is not None:
            filters.append(f"to_publication_date:{query.year_to}-12-31")
        if query.language:
            filters.append(f"language:{query.language}")
        # Priorizar recursos de acceso abierto (descargables).
        filters.append("is_oa:true")

        params: dict[str, str] = {
            "search": query.query,
            "per-page": str(min(query.limit, 200)),
            "filter": ",".join(filters),
        }
        settings = get_settings()
        if settings.contact_email:
            params["mailto"] = settings.contact_email
        return params

    def _parse_work(self, work: dict, query: SearchQuery) -> ResourceItem | None:
        location = work.get("primary_location") or {}
        best_oa = work.get("best_oa_location") or {}
        download_url = best_oa.get("pdf_url") or location.get("pdf_url")
        landing_url = (
            best_oa.get("landing_page_url")
            or location.get("landing_page_url")
            or work.get("id")
        )

        file_type = self.infer_file_type(download_url)
        if download_url and file_type == FileType.ANY:
            file_type = FileType.PDF  # OpenAlex OA suele servir PDFs
        if not self.matches_file_type(file_type, query.file_types):
            return None

        source_obj = location.get("source") or {}
        repository = source_obj.get("display_name") or self.host_of(landing_url)

        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in work.get("authorships", [])
        ]

        return ResourceItem(
            title=work.get("title") or work.get("display_name") or "Sin título",
            authors=[a for a in authors if a][:8],
            year=work.get("publication_year"),
            language=work.get("language"),
            description=self._reconstruct_abstract(work.get("abstract_inverted_index")),
            landing_url=landing_url,
            download_url=download_url,
            file_type=file_type,
            source=self.name,
            repository=repository,
            open_access=bool((work.get("open_access") or {}).get("is_oa")),
            relevance=float(work.get("relevance_score") or 0.0),
        )

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
        """Reconstruye el resumen desde el índice invertido de OpenAlex."""
        if not inverted_index:
            return None
        positions: list[tuple[int, str]] = []
        for word, idxs in inverted_index.items():
            for idx in idxs:
                positions.append((idx, word))
        positions.sort(key=lambda pair: pair[0])
        abstract = " ".join(word for _, word in positions)
        return abstract[:1000] if abstract else None
