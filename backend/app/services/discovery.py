"""Descubrimiento de repositorios de acceso abierto con endpoint OAI-PMH.

Estrategia en dos capas:

1. Un **catálogo semilla** curado (funciona sin red ni claves) con repositorios
   académicos conocidos y su endpoint OAI-PMH.
2. Si se configura `OPENDOAR_API_KEY`, se consulta el directorio OpenDOAR
   (Sherpa) para descubrir muchos más repositorios dinámicamente.

Los endpoints marcados con `verified=False` deben confirmarse antes de cosechar
(la convención DSpace es `<host>/oai/request` u `<host>/server/oai/request`).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import get_settings
from app.core.security import build_http_client
from app.models.schemas import RepositoryInfo
from app.services.oai_resolver import resolve_endpoint

logger = logging.getLogger(__name__)

# Catálogo semilla curado (verificar el endpoint antes de cosechar en producción).
SEED_CATALOG: list[RepositoryInfo] = [
    RepositoryInfo(
        name="arXiv",
        country="Global",
        oai_base_url="http://export.arxiv.org/oai2",
        homepage="https://arxiv.org",
        verified=True,
    ),
    RepositoryInfo(
        name="Zenodo (CERN)",
        country="Global",
        oai_base_url="https://zenodo.org/oai2d",
        homepage="https://zenodo.org",
        verified=True,
    ),
    RepositoryInfo(
        name="Universidad de los Andes (Colombia)",
        country="Colombia",
        oai_base_url="https://repositorio.uniandes.edu.co/server/oai/request",
        homepage="https://repositorio.uniandes.edu.co",
    ),
    RepositoryInfo(
        name="UNAM (México)",
        country="México",
        oai_base_url="https://repositorio.unam.mx/oai",
        homepage="https://repositorio.unam.mx",
    ),
    RepositoryInfo(
        name="MIT DSpace",
        country="EE. UU.",
        oai_base_url="https://dspace.mit.edu/oai/request",
        homepage="https://dspace.mit.edu",
    ),
]

OPENDOAR_API = "https://v2.sherpa.ac.uk/cgi/retrieve"


class DiscoveryService:
    """Busca repositorios por nombre o país."""

    async def search(
        self,
        query: str | None = None,
        country: str | None = None,
        verify: bool = True,
    ) -> list[RepositoryInfo]:
        results = self._filter(SEED_CATALOG, query, country)

        settings = get_settings()
        if settings.opendoar_api_key:
            try:
                results = self._merge(results, await self._opendoar(query, country))
            except httpx.HTTPError as exc:
                logger.warning("OpenDOAR no disponible: %s", exc)

        if verify:
            results = await self._verify_live(results)
        return results

    async def _verify_live(
        self, repos: list[RepositoryInfo]
    ) -> list[RepositoryInfo]:
        """Comprueba cada endpoint en vivo y devuelve sólo los que responden OAI.

        Además corrige la URL al endpoint que realmente funciona (p. ej. de
        `/oai/request` a `/server/oai/request`) y los marca como verificados.
        Si la comprobación falla por un fallo de red puntual, el repositorio se
        descarta para no ofrecer endpoints muertos.
        """
        if not repos:
            return repos

        settings = get_settings()
        semaphore = asyncio.Semaphore(8)
        timeout = httpx.Timeout(12.0, connect=6.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
            max_redirects=settings.http_max_redirects,
        ) as client:

            async def check(repo: RepositoryInfo) -> RepositoryInfo | None:
                async with semaphore:
                    try:
                        resolved = await resolve_endpoint(client, repo.oai_base_url)
                    except httpx.HTTPError:
                        resolved = None
                if resolved is None:
                    logger.info("Descartado repo sin OAI vivo: %s", repo.name)
                    return None
                return repo.model_copy(
                    update={"oai_base_url": resolved, "verified": True}
                )

            checked = await asyncio.gather(*(check(r) for r in repos))

        return [r for r in checked if r is not None]

    @staticmethod
    def _filter(
        items: list[RepositoryInfo], query: str | None, country: str | None
    ) -> list[RepositoryInfo]:
        q = (query or "").strip().lower()
        c = (country or "").strip().lower()
        out = []
        for item in items:
            if q and q not in item.name.lower():
                continue
            if c and (not item.country or c not in item.country.lower()):
                continue
            out.append(item)
        return out

    @staticmethod
    def _merge(
        base: list[RepositoryInfo], extra: list[RepositoryInfo]
    ) -> list[RepositoryInfo]:
        seen = {r.oai_base_url for r in base}
        for item in extra:
            if item.oai_base_url not in seen:
                base.append(item)
                seen.add(item.oai_base_url)
        return base

    async def _opendoar(
        self, query: str | None, country: str | None
    ) -> list[RepositoryInfo]:
        """Consulta OpenDOAR (best-effort; requiere clave de API)."""
        settings = get_settings()
        params = {
            "item-type": "repository",
            "api-key": settings.opendoar_api_key or "",
            "format": "Json",
        }
        async with build_http_client() as client:
            response = await client.get(OPENDOAR_API, params=params)
            response.raise_for_status()
            payload = response.json()

        results: list[RepositoryInfo] = []
        for item in payload.get("items", []):
            oai = item.get("oai_url") or item.get("oai")
            if not oai:
                continue
            results.append(
                RepositoryInfo(
                    name=item.get("name", [{}])[0].get("name", "Repositorio")
                    if isinstance(item.get("name"), list)
                    else str(item.get("name", "Repositorio")),
                    country=(item.get("country") or [None])[0]
                    if isinstance(item.get("country"), list)
                    else item.get("country"),
                    oai_base_url=oai,
                    homepage=item.get("url"),
                    verified=False,
                )
            )
        return self._filter(results, query, country)
