"""Contrato base para los conectores de fuentes abiertas.

Cada fuente (OpenAlex, arXiv, ...) implementa este protocolo. Añadir una nueva
fuente es tan simple como crear una clase que herede de `BaseSource` y
registrarla en el agregador.
"""

from __future__ import annotations

import abc
from urllib.parse import urlparse

import httpx

from app.models.schemas import FileType, ResourceItem, SearchQuery, SourceName


class BaseSource(abc.ABC):
    """Interfaz común que implementan todas las fuentes."""

    name: SourceName

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @abc.abstractmethod
    async def search(self, query: SearchQuery) -> list[ResourceItem]:
        """Ejecuta la búsqueda en la fuente y devuelve recursos normalizados."""
        raise NotImplementedError

    @staticmethod
    def host_of(url: str | None) -> str | None:
        """Extrae el host de una URL para identificar el repositorio."""
        if not url:
            return None
        try:
            return urlparse(url).netloc or None
        except ValueError:
            return None

    @staticmethod
    def infer_file_type(url: str | None) -> FileType:
        """Infiere el tipo de archivo a partir de la extensión de la URL."""
        if not url:
            return FileType.ANY
        lowered = url.lower()
        if lowered.endswith(".pdf"):
            return FileType.PDF
        if lowered.endswith((".doc", ".docx")):
            return FileType.WORD
        if lowered.endswith((".ppt", ".pptx")):
            return FileType.PRESENTATION
        return FileType.ANY

    @staticmethod
    def matches_file_type(item_type: FileType, wanted: list[FileType]) -> bool:
        """Indica si un recurso encaja con los tipos de archivo solicitados."""
        if not wanted or FileType.ANY in wanted:
            return True
        return item_type in wanted
