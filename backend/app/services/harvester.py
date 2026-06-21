"""Cosechador OAI-PMH de repositorios universitarios.

OAI-PMH (Open Archives Initiative – Protocol for Metadata Harvesting) es el
estándar que exponen los repositorios institucionales (DSpace, EPrints, etc.)
para cosechar sus metadatos de forma masiva y *legal*. Es la manera correcta de
indexar miles de manuales y cartillas abiertas a escala, sin scraping agresivo.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from app.config import get_settings
from app.core.net_safety import UnsafeUrlError, assert_safe_url
from app.models.schemas import (
    FileType,
    HarvestRequest,
    ResourceItem,
    SourceName,
)

logger = logging.getLogger(__name__)

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# Marcadores habituales de acceso abierto en el campo dc:rights.
_OPEN_MARKERS = ("open access", "openaccess", "acceso abierto", "openaccess")
_OPEN_URI = "info:eu-repo/semantics/openaccess"


class OaiPmhHarvester:
    """Cosecha registros Dublin Core desde un endpoint OAI-PMH."""

    async def harvest(
        self, request: HarvestRequest
    ) -> tuple[list[ResourceItem], list[str]]:
        warnings: list[str] = []
        try:
            await assert_safe_url(request.base_url)
        except UnsafeUrlError as exc:
            return [], [f"URL no permitida: {exc}"]

        settings = get_settings()
        cap = min(request.max_records, settings.max_harvest_records)
        repository = urlparse(request.base_url).netloc

        items: list[ResourceItem] = []
        params: dict[str, str] = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        if request.set_spec:
            params["set"] = request.set_spec

        timeout = httpx.Timeout(settings.http_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
            max_redirects=settings.http_max_redirects,
        ) as client:
            while len(items) < cap:
                try:
                    response = await client.get(request.base_url, params=params)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    warnings.append(f"El repositorio no respondió: {exc}")
                    break

                root, error = self._parse(response.text)
                if error:
                    if error != "noRecordsMatch":
                        warnings.append(f"OAI-PMH: {error}")
                    break
                if root is None:
                    warnings.append("Respuesta OAI-PMH ilegible.")
                    break

                for record in root.findall(".//oai:record", NS):
                    item = self._parse_record(record, request, repository)
                    if item is not None:
                        items.append(item)
                        if len(items) >= cap:
                            break

                token_el = root.find(".//oai:resumptionToken", NS)
                token = token_el.text.strip() if token_el is not None and token_el.text else None
                if not token:
                    break
                # Con resumptionToken NO se reenvían los demás parámetros.
                params = {"verb": "ListRecords", "resumptionToken": token}

        return items, warnings

    @staticmethod
    def _parse(xml_text: str) -> tuple[ET.Element | None, str | None]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None, None
        error = root.find("oai:error", NS)
        if error is not None:
            return None, error.get("code") or "error"
        return root, None

    def _parse_record(
        self, record: ET.Element, request: HarvestRequest, repository: str
    ) -> ResourceItem | None:
        header = record.find("oai:header", NS)
        if header is not None and header.get("status") == "deleted":
            return None

        dc = record.find(".//oai_dc:dc", NS)
        if dc is None:
            return None

        def values(tag: str) -> list[str]:
            return [
                el.text.strip()
                for el in dc.findall(f"dc:{tag}", NS)
                if el.text and el.text.strip()
            ]

        rights = values("rights")
        open_access = self._is_open_access(rights)
        if request.only_open_access and not open_access:
            return None

        language = (values("language") or [None])[0]
        if request.language and language and not language.lower().startswith(
            request.language.lower()
        ):
            return None

        year = self._extract_year(values("date"))
        if request.year_from and (year is None or year < request.year_from):
            return None
        if request.year_to and (year is None or year > request.year_to):
            return None

        identifiers = values("identifier")
        download_url = next(
            (u for u in identifiers if u.lower().split("?")[0].endswith(".pdf")),
            None,
        )
        landing_url = next(
            (u for u in identifiers if u.startswith("http")), None
        )

        titles = values("title")
        return ResourceItem(
            title=titles[0] if titles else "Sin título",
            authors=values("creator")[:8],
            year=year,
            language=language,
            description=(values("description") or [None])[0],
            landing_url=landing_url,
            download_url=download_url,
            file_type=FileType.PDF if download_url else FileType.REPOSITORY,
            source=SourceName.OAI,
            repository=repository,
            open_access=open_access,
            relevance=0.0,
        )

    @staticmethod
    def _is_open_access(rights: list[str]) -> bool:
        for value in rights:
            lowered = value.lower()
            if _OPEN_URI in lowered or any(m in lowered for m in _OPEN_MARKERS):
                return True
        return False

    @staticmethod
    def _extract_year(dates: list[str]) -> int | None:
        for value in dates:
            if len(value) >= 4 and value[:4].isdigit():
                return int(value[:4])
        return None
