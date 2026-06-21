"""Conector de arXiv (https://arxiv.org).

arXiv ofrece una API Atom abierta y gratuita con cientos de miles de artículos
científicos en PDF. No requiere clave de API.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

import httpx

from app.models.schemas import FileType, ResourceItem, SearchQuery, SourceName
from app.services.sources.base import BaseSource

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivSource(BaseSource):
    """Busca artículos científicos en arXiv."""

    name = SourceName.ARXIV

    async def search(self, query: SearchQuery) -> list[ResourceItem]:
        # arXiv solo indexa contenido en inglés; si se pide otro idioma, se omite.
        if query.language and query.language != "en":
            return []

        params = {
            "search_query": f"all:{query.query}",
            "start": "0",
            "max_results": str(min(query.limit, 100)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            response = await self._client.get(ARXIV_API, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("arXiv no disponible: %s", exc)
            return []

        return self._parse_feed(response.text, query)

    def _parse_feed(self, xml_text: str, query: SearchQuery) -> list[ResourceItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("Respuesta de arXiv ilegible: %s", exc)
            return []

        results: list[ResourceItem] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            item = self._parse_entry(entry, query)
            if item is not None:
                results.append(item)
        return results

    def _parse_entry(self, entry: ET.Element, query: SearchQuery) -> ResourceItem | None:
        # arXiv siempre sirve PDF; respetar el filtro de tipo de archivo.
        if not self.matches_file_type(FileType.PDF, query.file_types):
            return None

        title = self._text(entry, "atom:title") or "Sin título"
        summary = self._text(entry, "atom:summary")
        published = self._text(entry, "atom:published")
        year = int(published[:4]) if published and published[:4].isdigit() else None

        if query.year_from and (year is None or year < query.year_from):
            return None
        if query.year_to and (year is None or year > query.year_to):
            return None

        landing_url = self._text(entry, "atom:id")
        download_url = None
        for link in entry.findall("atom:link", ATOM_NS):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                download_url = link.get("href")
                break

        authors = [
            self._text(author, "atom:name") or ""
            for author in entry.findall("atom:author", ATOM_NS)
        ]

        return ResourceItem(
            title=" ".join(title.split()),
            authors=[a for a in authors if a][:8],
            year=year,
            language="en",
            description=" ".join(summary.split())[:1000] if summary else None,
            landing_url=landing_url,
            download_url=download_url,
            file_type=FileType.PDF,
            source=self.name,
            repository="arXiv.org",
            open_access=True,
            relevance=0.0,
        )

    @staticmethod
    def _text(element: ET.Element, path: str) -> str | None:
        found = element.find(path, ATOM_NS)
        return found.text.strip() if found is not None and found.text else None
