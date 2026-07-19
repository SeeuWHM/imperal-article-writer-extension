"""cache_helpers.cached_call — unit tests, no network."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from cache_helpers import cached_call


class _FakeCacheClient:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.fetch_calls = 0

    async def get_or_fetch(self, key, model, fetcher, ttl_seconds=60):
        if key in self.store:
            return self.store[key]
        self.fetch_calls += 1
        value = await fetcher()
        self.store[key] = value
        return value


def _ctx_with_cache():
    ctx = SimpleNamespace()
    ctx.cache = _FakeCacheClient()
    return ctx


@pytest.mark.asyncio
async def test_cached_call_fetches_once_then_serves_from_cache():
    ctx = _ctx_with_cache()
    calls = []

    async def fetcher():
        calls.append(1)
        return {"data": [{"id": "p1", "name": "Project A"}]}

    first = await cached_call(ctx, "projects", "tenant-1", None, 60, fetcher)
    second = await cached_call(ctx, "projects", "tenant-1", None, 60, fetcher)

    assert first == {"data": [{"id": "p1", "name": "Project A"}]}
    assert second == first
    assert len(calls) == 1
    assert ctx.cache.fetch_calls == 1


@pytest.mark.asyncio
async def test_cached_call_keys_differ_per_user_and_extra():
    ctx = _ctx_with_cache()

    async def fetcher_a():
        return {"data": ["a"]}

    async def fetcher_b():
        return {"data": ["b"]}

    r1 = await cached_call(ctx, "articles_board", "tenant-1", {"project_id": "p1"}, 60, fetcher_a)
    r2 = await cached_call(ctx, "articles_board", "tenant-2", {"project_id": "p1"}, 60, fetcher_b)
    r3 = await cached_call(ctx, "articles_board", "tenant-1", {"project_id": "p2"}, 60, fetcher_b)

    assert r1 == {"data": ["a"]}
    assert r2 == {"data": ["b"]}
    assert r3 == {"data": ["b"]}
    assert ctx.cache.fetch_calls == 3


@pytest.mark.asyncio
async def test_cached_call_falls_back_when_cache_unavailable():
    class _NoCacheCtx:
        @property
        def cache(self):
            raise RuntimeError("no cache in this context")

    ctx = _NoCacheCtx()
    calls = []

    async def fetcher():
        calls.append(1)
        return {"data": []}

    result = await cached_call(ctx, "projects", "tenant-1", None, 60, fetcher)
    assert result == {"data": []}
    assert len(calls) == 1
