"""Protección contra SSRF para descargas de URLs externas.

Antes de descargar cualquier URL suministrada por el usuario o cosechada de un
repositorio, validamos que:

- El esquema sea http/https.
- El host NO resuelva a una dirección privada, de loopback, link-local o
  reservada (evita que la herramienta sea usada para alcanzar servicios internos
  de la red — un vector clásico de SSRF).

La validación de redirecciones se hace salto a salto en el descargador, porque
una URL pública puede redirigir a una interna.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """La URL no es segura para ser descargada."""


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


async def assert_safe_url(url: str) -> None:
    """Lanza UnsafeUrlError si la URL no es segura para descargar."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Esquema no permitido: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL sin host.")

    # Resolver el host (operación bloqueante → hilo aparte).
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"No se pudo resolver el host {host!r}.") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeUrlError(f"El host {host!r} no resolvió a ninguna IP.")
    for ip in addresses:
        if not _is_public_ip(ip):
            raise UnsafeUrlError(
                f"El host {host!r} resuelve a una dirección no pública ({ip})."
            )
