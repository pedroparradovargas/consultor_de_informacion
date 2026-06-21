"""Rutas de la API REST."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import rate_limit
from app.models.schemas import SearchQuery, SearchResponse, SourceName
from app.services.aggregator import SearchAggregator

router = APIRouter()
_aggregator = SearchAggregator()


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
