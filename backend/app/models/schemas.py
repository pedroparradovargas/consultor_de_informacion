"""Modelos de datos (contratos de la API) validados con Pydantic.

Estos esquemas definen tanto la petición de búsqueda como la forma de los
resultados. Pydantic garantiza validación y saneamiento automático de toda
entrada del usuario antes de que llegue a la lógica de negocio.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FileType(str, enum.Enum):
    """Tipos de archivo que el usuario puede solicitar."""

    PDF = "pdf"
    WORD = "word"
    PRESENTATION = "presentation"
    REPOSITORY = "repository"
    ANY = "any"


class SourceName(str, enum.Enum):
    """Fuentes abiertas soportadas por el motor de búsqueda."""

    OPENALEX = "openalex"
    ARXIV = "arxiv"
    OAI = "oai"  # repositorios universitarios vía OAI-PMH


class SearchQuery(BaseModel):
    """Parámetros de una búsqueda de recursos educativos."""

    query: str = Field(
        ...,
        min_length=2,
        max_length=256,
        description="Temario o palabras clave a buscar.",
        examples=["redes neuronales", "cálculo diferencial"],
    )
    year_from: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Año inicial del lapso de búsqueda.",
    )
    year_to: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Año final del lapso de búsqueda.",
    )
    language: str | None = Field(
        default=None,
        min_length=2,
        max_length=5,
        description="Código ISO 639-1 del idioma (ej. 'es', 'en').",
        examples=["es", "en"],
    )
    file_types: list[FileType] = Field(
        default_factory=lambda: [FileType.ANY],
        description="Tipos de archivo deseados.",
    )
    sources: list[SourceName] = Field(
        default_factory=lambda: [SourceName.OPENALEX, SourceName.ARXIV],
        description="Fuentes abiertas a consultar.",
    )
    limit: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Número máximo de resultados.",
    )

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La consulta no puede estar vacía.")
        return cleaned

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: str | None) -> str | None:
        return value.lower().strip() if value else None

    def validate_year_range(self) -> None:
        """Valida coherencia del rango de años (lanza ValueError si es inválido)."""
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("'year_from' no puede ser mayor que 'year_to'.")


class ResourceItem(BaseModel):
    """Un recurso educativo encontrado."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    language: str | None = None
    description: str | None = None
    landing_url: str | None = None
    download_url: str | None = None
    file_type: FileType = FileType.ANY
    source: SourceName
    repository: str | None = Field(
        default=None,
        description="Host/repositorio donde está alojado el recurso.",
    )
    open_access: bool = False
    relevance: float = Field(default=0.0, ge=0.0)


class SearchResponse(BaseModel):
    """Respuesta del endpoint de búsqueda."""

    query: SearchQuery
    total: int
    results: list[ResourceItem]
    took_ms: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
#  Cosecha OAI-PMH y descarga de PDFs de repositorios abiertos
# --------------------------------------------------------------------------


class HarvestRequest(BaseModel):
    """Parámetros para cosechar metadatos de un repositorio vía OAI-PMH."""

    base_url: str = Field(
        ...,
        description="Endpoint OAI-PMH del repositorio (ej. https://repo.uni.edu/oai/request).",
        examples=["https://repositorio.unal.edu.co/oai/request"],
    )
    set_spec: str | None = Field(
        default=None, description="Colección/set OAI-PMH a cosechar (opcional)."
    )
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    language: str | None = Field(default=None, min_length=2, max_length=5)
    only_open_access: bool = Field(
        default=True,
        description="Cosechar únicamente registros marcados como acceso abierto.",
    )
    max_records: int = Field(default=100, ge=1, le=500)


class HarvestResponse(BaseModel):
    """Resultado de una cosecha OAI-PMH."""

    base_url: str
    total: int
    results: list[ResourceItem]
    took_ms: int
    warnings: list[str] = Field(default_factory=list)


class DownloadStatus(str, enum.Enum):
    """Estado de la descarga de un recurso."""

    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"


class DownloadRequest(BaseModel):
    """Solicitud de descarga de PDFs de acceso abierto."""

    urls: list[str] = Field(..., min_length=1, description="URLs de PDFs a descargar.")


class DownloadResultItem(BaseModel):
    """Resultado de descargar una URL."""

    url: str
    status: DownloadStatus
    reason: str | None = None
    path: str | None = None
    size_bytes: int | None = None


class DownloadResponse(BaseModel):
    """Resultado de un lote de descargas."""

    total: int
    downloaded: int
    results: list[DownloadResultItem]
    download_dir: str
