"""Job queue interface, asyncio worker, and cache."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import CacheEntry, Job
from app.db.session import session_factory


class JobQueue(Protocol):
    async def enqueue(self, db: AsyncSession, user_id: str, job_type: str, payload: dict[str, Any]) -> Job: ...
    async def get(self, db: AsyncSession, job_id: str, user_id: str) -> Job | None: ...


class AsyncioJobQueue:
    async def enqueue(self, db: AsyncSession, user_id: str, job_type: str, payload: dict[str, Any]) -> Job:
        job = Job(user_id=user_id, type=job_type, payload_json=payload, status="queued")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def get(self, db: AsyncSession, job_id: str, user_id: str) -> Job | None:
        result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user_id))
        return result.scalar_one_or_none()


job_queue = AsyncioJobQueue()


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        value, expires = item
        if expires < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (value, time.time() + ttl_seconds)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class DbCache:
    async def get(self, key: str) -> Any | None:
        async with session_factory() as db:
            result = await db.execute(select(CacheEntry).where(CacheEntry.key == key))
            entry = result.scalar_one_or_none()
            if not entry:
                return None
            expires = entry.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                await db.delete(entry)
                await db.commit()
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        async with session_factory() as db:
            result = await db.execute(select(CacheEntry).where(CacheEntry.key == key))
            entry = result.scalar_one_or_none()
            if entry:
                entry.value = value
                entry.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            else:
                db.add(CacheEntry(key=key, value=value, expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)))
            await db.commit()

    async def delete(self, key: str) -> None:
        async with session_factory() as db:
            result = await db.execute(select(CacheEntry).where(CacheEntry.key == key))
            entry = result.scalar_one_or_none()
            if entry:
                await db.delete(entry)
                await db.commit()


memory_cache = InMemoryCache()
db_cache = DbCache()


async def get_cache(key: str) -> Any | None:
    value = await memory_cache.get(key)
    if value is not None:
        return value
    value = await db_cache.get(key)
    if value is not None:
        await memory_cache.set(key, value, settings.cache_ttl_search_seconds)
    return value


async def set_cache(key: str, value: Any, ttl_seconds: int) -> None:
    await memory_cache.set(key, value, ttl_seconds)
    await db_cache.set(key, value, ttl_seconds)


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._process_once()
            except Exception:
                pass
            await asyncio.sleep(settings.job_poll_interval_seconds)

    async def _process_once(self) -> None:
        async with session_factory() as db:
            result = await db.execute(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1))
            job = result.scalar_one_or_none()
            if not job:
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.attempts += 1
            await db.commit()
            try:
                if job.type == "verification":
                    from app.services.verification_service import run_verification_job

                    await run_verification_job(db, job)
                else:
                    job.status = "failed"
                    job.error = f"Unknown job type: {job.type}"
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


job_worker = JobWorker()
