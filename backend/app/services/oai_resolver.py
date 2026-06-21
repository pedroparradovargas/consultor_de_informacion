"""Resolución de endpoints OAI-PMH.

Lógica compartida por el cosechador y el descubrimiento de repositorios. Dado
lo que el usuario (o un catálogo) cree que es el endpoint OAI, prueba las rutas
habituales y devuelve la primera que responde como un endpoint OAI-PMH real.

DSpace 7+ movió OAI de `/oai/request` a `/server/oai/request`; muchas URLs
antiguas devuelven 404 (a menudo la propia SPA del repositorio con estado 404).
Por eso comprobamos el cuerpo: sólo es OAI si contiene el espacio de nombres
OAI-PMH, no basta con que el código de estado no sea 404.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx


def candidate_endpoints(base_url: str) -> list[str]:
    """Genera rutas candidatas a partir de la URL indicada."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")

    candidates: list[str] = [base_url.rstrip("/")]
    # Variantes derivadas de la ruta dada.
    if path.endswith("/oai/request") and "/server/" not in path:
        candidates.append(root + path.replace("/oai/request", "/server/oai/request"))
    if path.endswith("/oai") and "/server/" not in path:
        candidates.append(root + path + "/request")
        candidates.append(root + "/server/oai/request")
    # Rutas estándar como respaldo (DSpace 7+, DSpace 6, EPrints).
    candidates.extend(
        [
            f"{root}/server/oai/request",
            f"{root}/oai/request",
            f"{root}/oai",
            f"{root}/cgi/oai2",
        ]
    )

    # Dedup conservando el orden.
    seen: set[str] = set()
    ordered: list[str] = []
    for url in candidates:
        normalized = urlunparse(urlparse(url))
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(url)
    return ordered


def is_oai_response(text: str) -> bool:
    """¿El cuerpo es realmente una respuesta OAI-PMH?"""
    return "<OAI-PMH" in text or "openarchives.org/OAI" in text


async def resolve_endpoint(client: httpx.AsyncClient, base_url: str) -> str | None:
    """Devuelve el endpoint OAI-PMH válido (probando candidatos) o None."""
    for candidate in candidate_endpoints(base_url):
        try:
            response = await client.get(candidate, params={"verb": "Identify"})
        except httpx.HTTPError:
            continue
        if response.status_code == 404:
            continue
        if is_oai_response(response.text):
            return candidate
    return None
