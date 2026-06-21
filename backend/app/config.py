"""Configuración central de la aplicación.

Toda la configuración se carga desde variables de entorno (o un archivo .env),
siguiendo las buenas prácticas de 12-factor app. Nunca se incrustan secretos
en el código.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    download_dir: str = "downloads"
    download_concurrency: int = 5  # descargas simultáneas (global)
    per_domain_delay_seconds: float = 1.0  # espera mínima entre hits al mismo host
    max_download_mb: int = 50  # tamaño máximo por archivo
    max_download_urls: int = 50  # URLs por petición
    download_retries: int = 3  # reintentos con backoff exponencial
    respect_robots: bool = True  # respetar robots.txt (recomendado)
    max_harvest_records: int = 200  # tope de registros por cosecha OAI-PMH


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única (cacheada) de la configuración."""
    return Settings()
