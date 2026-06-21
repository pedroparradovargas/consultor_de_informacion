"""Rutas de la API REST."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.core.security import rate_limit
from app.models.schemas import (
    DownloadRequest,
    DownloadResponse,
    DownloadStatus,
    HarvestRequest,
    HarvestResponse,
    SearchQuery,
    SearchResponse,
    SourceName,
)
from app.services.aggregator import SearchAggregator
from app.services.downloader import Downloader
from app.services.harvester import OaiPmhHarvester

router = APIRouter()
_aggregator = SearchAggregator()
_harvester = OaiPmhHarvester()


@router.get("/health", tags=["sistema"], summary="Estado del servicio")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/sources", tags=["búsqueda"], summary="Fuentes disponibles")
async def list_sources() -> list[dict[str, str]]:
    return [
        {"id": SourceName.OPENALEX.value, "name": "OpenAlex", "type": "API abierta"},
        {"id": SourceName.ARXIV.value, "name": "arXiv", "type": "API abierta"},
    ]


@router.post(
    "/search",
    response_model=SearchResponse,
    tags=["búsqueda"],
    summary="Buscar recursos educativos en fuentes abiertas",
    dependencies=[Depends(rate_limit)],
)
async def search(query: SearchQuery) -> SearchResponse:
    """Ejecuta una búsqueda agregada sobre las fuentes seleccionadas."""
    try:
        query.validate_year_range()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    started = time.perf_counter()
    results, warnings = await _aggregator.run(query)
    took_ms = int((time.perf_counter() - started) * 1000)

    return SearchResponse(
        query=query,
        total=len(results),
        results=results,
        took_ms=took_ms,
        warnings=warnings,
    )


@router.post(
    "/harvest",
    response_model=HarvestResponse,
    tags=["repositorios"],
    summary="Cosechar metadatos de un repositorio universitario (OAI-PMH)",
    dependencies=[Depends(rate_limit)],
)
async def harvest(request: HarvestRequest) -> HarvestResponse:
    """Cosecha registros de acceso abierto de un repositorio vía OAI-PMH."""
    started = time.perf_counter()
    results, warnings = await _harvester.harvest(request)
    took_ms = int((time.perf_counter() - started) * 1000)
    return HarvestResponse(
        base_url=request.base_url,
        total=len(results),
        results=results,
        took_ms=took_ms,
        warnings=warnings,
    )


@router.post(
    "/download",
    response_model=DownloadResponse,
    tags=["repositorios"],
    summary="Descargar PDFs de acceso abierto de forma responsable",
    dependencies=[Depends(rate_limit)],
)
async def download(request: DownloadRequest) -> DownloadResponse:
    """Descarga PDFs (solo acceso abierto) respetando robots.txt y rate limiting."""
    settings = get_settings()
    if len(request.urls) > settings.max_download_urls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Máximo {settings.max_download_urls} URLs por petición.",
        )

    downloader = Downloader(settings)
    results = await downloader.download_many([str(u) for u in request.urls])
    downloaded = sum(1 for r in results if r.status == DownloadStatus.DOWNLOADED)
    return DownloadResponse(
        total=len(results),
        downloaded=downloaded,
        results=results,
        download_dir=settings.download_dir,
    )
