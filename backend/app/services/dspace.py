"""Resolución de PDFs descargables en repositorios DSpace 7+.

Los metadatos OAI-PMH (Dublin Core) de DSpace sólo exponen la URL de la *página*
del ítem (un handle), no el PDF. Para poder descargar el libro directamente,
usamos la **API REST de DSpace 7** para localizar el archivo (bitstream) PDF:

    handle ─▶ /server/api/pid/find ─▶ item uuid
           ─▶ /server/api/core/items/{uuid}/bundles ─▶ bundle "ORIGINAL"
           ─▶ /server/api/core/bundles/{uuid}/bitstreams ─▶ bitstream PDF
           ─▶ /server/api/core/bitstreams/{uuid}/content   (descarga directa)

Es best-effort: si el repositorio no es DSpace 7 o algún paso falla, devolvemos
None y el registro simplemente queda sin enlace de descarga directa.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_HANDLE_RE = re.compile(r"handle\.net/(?P<handle>\d+/\d+)")
_ITEM_RE = re.compile(r"/items/(?P<uuid>[0-9a-fA-F-]{36})")


class DSpaceResolver:
    """Localiza el PDF descargable de un ítem DSpace vía su API REST."""

    def __init__(self, client: httpx.AsyncClient, root_url: str) -> None:
        self._client = client
        self._root = root_url.rstrip("/")
        self._api = f"{self._root}/server/api"

    @staticmethod
    def root_from_oai(oai_url: str) -> str:
        parsed = urlparse(oai_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def resolve_pdf(self, landing_url: str) -> str | None:
        """Devuelve la URL de descarga directa del PDF, o None."""
        try:
            uuid = await self._item_uuid(landing_url)
            if uuid is None:
                return None
            bundle_uuid = await self._original_bundle(uuid)
            if bundle_uuid is None:
                return None
            return await self._pdf_bitstream(bundle_uuid)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.debug("DSpace: no se pudo resolver %s (%s)", landing_url, exc)
            return None

    async def _item_uuid(self, landing_url: str) -> str | None:
        # Caso 1: la URL ya apunta al ítem por UUID.
        item_match = _ITEM_RE.search(landing_url)
        if item_match:
            return item_match.group("uuid")

        # Caso 2: handle → resolver a UUID.
        handle_match = _HANDLE_RE.search(landing_url)
        if not handle_match:
            return None
        response = await self._get(
            f"{self._api}/pid/find", params={"id": f"hdl:{handle_match.group('handle')}"}
        )
        if response is None:
            return None
        return response.json().get("uuid")

    async def _original_bundle(self, item_uuid: str) -> str | None:
        response = await self._get(f"{self._api}/core/items/{item_uuid}/bundles")
        if response is None:
            return None
        bundles = response.json().get("_embedded", {}).get("bundles", [])
        for bundle in bundles:
            if bundle.get("name") == "ORIGINAL":
                return bundle.get("uuid")
        return None

    async def _pdf_bitstream(self, bundle_uuid: str) -> str | None:
        response = await self._get(
            f"{self._api}/core/bundles/{bundle_uuid}/bitstreams"
        )
        if response is None:
            return None
        bitstreams = response.json().get("_embedded", {}).get("bitstreams", [])
        # Preferir un PDF; si no, el primer bitstream disponible.
        pdf = next(
            (b for b in bitstreams if (b.get("name") or "").lower().endswith(".pdf")),
            None,
        )
        chosen = pdf or (bitstreams[0] if bitstreams else None)
        if not chosen:
            return None
        return f"{self._api}/core/bitstreams/{chosen['uuid']}/content"

    async def _get(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response | None:
        response = await self._client.get(
            url, params=params, headers={"Accept": "application/json"}
        )
        if response.status_code != 200:
            return None
        return response
