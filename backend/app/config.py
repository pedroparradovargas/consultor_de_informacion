"""Configuración central de la aplicación.

Toda la configuración se carga desde variables de entorno (o un archivo .env),
siguiendo las buenas prácticas de 12-factor app. Nunca se incrustan secretos
en el código.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_download_dir() -> str:
    """Carpeta de descargas del usuario (Windows/macOS/Linux).

    Por defecto guardamos los libros en la carpeta «Descargas» del sistema,
    dentro de una subcarpeta propia para no mezclarlos con otros archivos.
    Se puede sobreescribir con la variable de entorno DOWNLOAD_DIR.
    """
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.exists() else Path.home()
    return str(base / "Consultor de Información")


class Settings(BaseSettings):
    """Ajustes de la aplicación validados con Pydantic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identidad de la API ---
    app_name: str = "Consultor de Información"
    app_version: str = "0.1.0"
    debug: bool = False

    # --- Red / HTTP ---
    # User-Agent identificable y honesto (buena práctica de scraping responsable).
    http_user_agent: str = (
        "ConsultorDeInformacion/0.1 (+https://github.com/pedroparradovargas/consultor_de_informacion) "
        "research-educational-tool"
    )
    http_timeout_seconds: float = 15.0
    http_max_redirects: int = 5

    # Correo de contacto para los servicios "polite pool" (ej. OpenAlex).
    contact_email: str | None = None

    # Clave de API de OpenDOAR (Sherpa) para descubrir repositorios (opcional).
    opendoar_api_key: str | None = None

    # --- CORS ---
    # Orígenes permitidos para el frontend (Angular dev server por defecto).
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]

    # --- Límites de seguridad ---
    rate_limit_requests: int = 30  # peticiones permitidas...
    rate_limit_window_seconds: int = 60  # ...por ventana de tiempo
    max_results_per_query: int = 100
    max_query_length: int = 256

    # --- Descargas / cosecha (scraping responsable) ---
    # Por defecto, la carpeta «Descargas» del usuario (ver _default_download_dir).
    download_dir: str = Field(default_factory=_default_download_dir)
    download_concurrency: int = 5  # descargas simultáneas (global)
    per_domain_delay_seconds: float = 1.0  # espera mínima entre hits al mismo host
    max_download_mb: int = 50  # tamaño máximo por archivo
    max_download_urls: int = 200  # URLs por petición
    download_retries: int = 3  # reintentos con backoff exponencial
    respect_robots: bool = True  # respetar robots.txt (recomendado)
    max_harvest_records: int = 200  # tope de registros por cosecha OAI-PMH


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única (cacheada) de la configuración."""
    return Settings()
