"""ctx.cache wrapper for Article Writer's panel reads.

The sidebar (project list) and workspace board (per-project articles list)
panels call the shared article-writer-api backend live on every single
render. Project/article METADATA (name, status, word_count — everything
shown in these two views) changes only when the user explicitly acts
(create/update/delete/status-change), and every such action already fires
a refresh_panels event (see panels_side.py / panels_workspace.py's
@ext.panel(..., refresh="on_event:...") declarations) that busts any stale
view instantly. So a short cache window here costs zero real staleness on
the events that matter, while saving a redundant backend round-trip on
every plain re-render (tab switch, unrelated panel refresh, etc).

The single-ARTICLE detail view (_render_article_view) is deliberately left
UNCACHED — that view is what's actively being generated/patched/edited, so
correctness there matters more than shaving one HTTP call.

ctx.cache TTL is platform-capped to [5, 300]s (I-CACHE-TTL-CAP-300S).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class CachedBackendPayload(BaseModel):
    """Generic ctx.cache envelope — one JSON-serialisable backend response."""
    data: Any = Field(default_factory=dict)


LIST_CACHE_TTL = 60  # projects / articles-board — busted instantly by refresh_panels events anyway


def _cache_key(scope: str, imperal_id: str, extra: dict | None = None) -> str:
    parts = {"scope": scope, "user": imperal_id, "extra": extra or {}}
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return f"aw:{digest}"


async def cached_call(ctx, scope: str, imperal_id: str, extra: dict | None,
                       ttl_seconds: int, fetcher: Callable[[], Awaitable[Any]]) -> Any:
    """Cache one JSON-serialisable payload behind ctx.cache.get_or_fetch().

    Falls back to calling the fetcher directly if ctx.cache is unavailable
    (e.g. a minimal test/mock Context) so callers never have to special-case it.
    """
    key = _cache_key(scope, imperal_id, extra)

    async def _fetch() -> CachedBackendPayload:
        return CachedBackendPayload(data=await fetcher())

    try:
        cache = ctx.cache
    except Exception:
        cache = None
    if cache is None:
        return await fetcher()

    payload = await cache.get_or_fetch(key, CachedBackendPayload, _fetch, ttl_seconds=ttl_seconds)
    return payload.data
