"""Gestor de trabajos de descarga con eventos de progreso en vivo.

Cada trabajo se ejecuta en segundo plano y publica eventos (start / progress /
done) en una cola asíncrona que el endpoint SSE transmite al navegador. El
estado se mantiene en memoria (suficiente para una sola instancia).
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.models.schemas import DownloadResultItem
from app.services.downloader import Downloader


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"


# Marca de fin de stream.
_SENTINEL: object = object()


@dataclass
class DownloadJob:
    """Estado de un trabajo de descarga."""

    id: str
    urls: list[str]
    state: JobState = JobState.QUEUED
    results: list[DownloadResultItem] = field(default_factory=list)
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    created_at: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return len(self.urls)

    @property
    def downloaded(self) -> int:
        from app.models.schemas import DownloadStatus

        return sum(1 for r in self.results if r.status == DownloadStatus.DOWNLOADED)


class JobManager:
    """Crea y ejecuta trabajos de descarga, exponiendo su progreso vía SSE."""

    def __init__(self, max_jobs: int = 200) -> None:
        self._jobs: dict[str, DownloadJob] = {}
        self._max_jobs = max_jobs

    def create(self, urls: list[str]) -> DownloadJob:
        """Registra el trabajo. La descarga arranca al abrir el stream SSE,
        de modo que la tarea de fondo y el consumidor compartan event loop."""
        self._evict_if_needed()
        job = DownloadJob(id=uuid.uuid4().hex, urls=urls)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        return self._jobs.get(job_id)

    async def _run(self, job: DownloadJob) -> None:
        await job.events.put(
            {"event": "start", "total": job.total, "job_id": job.id}
        )
        completed = 0

        async def on_result(result: DownloadResultItem) -> None:
            nonlocal completed
            completed += 1
            job.results.append(result)
            await job.events.put(
                {
                    "event": "progress",
                    "completed": completed,
                    "total": job.total,
                    "status": result.status.value,
                    "url": result.url,
                    "reason": result.reason,
                }
            )

        downloader = Downloader()
        try:
            await downloader.download_many(job.urls, on_result=on_result)
        finally:
            job.state = JobState.COMPLETED
            await job.events.put(
                {
                    "event": "done",
                    "total": job.total,
                    "downloaded": job.downloaded,
                    "download_dir": downloader.download_dir,
                }
            )
            await job.events.put(_SENTINEL)

    async def stream(self, job: DownloadJob) -> AsyncIterator[dict]:
        """Arranca el trabajo (si no lo está) e itera sus eventos hasta el final."""
        if job.state == JobState.QUEUED:
            job.state = JobState.RUNNING
            asyncio.create_task(self._run(job))
        while True:
            item = await job.events.get()
            if item is _SENTINEL:
                break
            yield item  # type: ignore[misc]

    def _evict_if_needed(self) -> None:
        if len(self._jobs) < self._max_jobs:
            return
        # Eliminar los trabajos completados más antiguos.
        completed = sorted(
            (j for j in self._jobs.values() if j.state == JobState.COMPLETED),
            key=lambda j: j.created_at,
        )
        for job in completed[: max(1, len(self._jobs) - self._max_jobs + 1)]:
            self._jobs.pop(job.id, None)


# Instancia única compartida por la aplicación.
job_manager = JobManager()
