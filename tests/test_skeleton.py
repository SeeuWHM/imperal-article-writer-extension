"""Skeleton change-alert logic — the proactive 'your article is ready'
notice. Pure old/new comparison, no backend/ctx needed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import skeleton

_ALERT = skeleton.skeleton_alert_article_writer_overview


@pytest.mark.asyncio
async def test_alert_fires_and_names_the_ready_article():
    old = {"by_status": {"review": 0}, "latest_ready": ""}
    new = {"by_status": {"review": 1}, "latest_ready": "Best VPS hosting 2026"}
    r = await _ALERT(None, old, new)
    assert "Best VPS hosting 2026" in r["response"]
    assert "ready for review" in r["response"]


@pytest.mark.asyncio
async def test_alert_plural_when_several_finish_at_once():
    old = {"by_status": {"review": 1}, "latest_ready": "A"}
    new = {"by_status": {"review": 3}, "latest_ready": "C"}
    r = await _ALERT(None, old, new)
    assert "2 articles" in r["response"]


@pytest.mark.asyncio
async def test_alert_silent_when_review_count_unchanged():
    snap = {"by_status": {"review": 2}, "latest_ready": "X"}
    assert (await _ALERT(None, snap, dict(snap)))["response"] == ""


@pytest.mark.asyncio
async def test_alert_silent_on_first_snapshot():
    new = {"by_status": {"review": 5}, "latest_ready": "X"}
    assert (await _ALERT(None, None, new))["response"] == ""


# ─── direct ctx.notify() path — the reliable one, see module docstring ────
# (2026-07-18: the kernel's own skeleton-diff alert above silently drops the
# next legitimate alert whenever the session workflow respawns the skeleton
# child mid-generation; skeleton_refresh_overview tracks its own baseline in
# ctx.store instead, which survives that respawn.)

class _FakeQueryResult:
    def __init__(self, docs):
        self.data = docs


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.data = data


class _FakeStore:
    def __init__(self, initial_review_count=None):
        self.doc = (
            _FakeDoc("d1", {"review_count": initial_review_count})
            if initial_review_count is not None else None
        )

    async def query(self, collection, limit=1):
        return _FakeQueryResult([self.doc] if self.doc else [])

    async def update(self, collection, doc_id, values):
        self.doc.data.update(values)

    async def create(self, collection, values):
        self.doc = _FakeDoc("d1", dict(values))


class _FakeCtx:
    def __init__(self, initial_review_count=None):
        self.store = _FakeStore(initial_review_count)
        self.notified: list[str] = []

    async def notify(self, message, **kwargs):
        self.notified.append(message)


def _fake_call_backend(articles):
    async def _call(ctx, method, path, params=None):
        if path == "/v1/projects":
            return {"data": [{"id": "p1", "name": "Site"}], "total": 1}
        if path == "/v1/articles":
            return {"data": articles, "total": len(articles)}
        raise AssertionError(f"unexpected path {path}")
    return _call


@pytest.mark.asyncio
async def test_refresh_notifies_when_review_count_increases(monkeypatch):
    articles = [{"id": "a1", "status": "review", "title": "New Article",
                 "updated_at": "2026-07-18T00:00:00"}]
    monkeypatch.setattr(skeleton, "call_backend", _fake_call_backend(articles))
    ctx = _FakeCtx(initial_review_count=0)
    await skeleton.skeleton_refresh_overview(ctx)
    assert ctx.notified == [
        'Your article "New Article" is written and ready for review in the Article Writer panel.'
    ]
    assert ctx.store.doc.data["review_count"] == 1


@pytest.mark.asyncio
async def test_refresh_seeds_baseline_without_notifying_on_first_ever_run(monkeypatch):
    """No persisted doc yet (doc_id is None) — nothing "just finished", we
    simply have no prior snapshot. Must seed silently, never notify."""
    articles = [{"id": "a1", "status": "review", "title": "Already There",
                 "updated_at": "2026-07-18T00:00:00"}]
    monkeypatch.setattr(skeleton, "call_backend", _fake_call_backend(articles))
    ctx = _FakeCtx(initial_review_count=None)
    await skeleton.skeleton_refresh_overview(ctx)
    assert ctx.notified == []
    assert ctx.store.doc.data["review_count"] == 1


@pytest.mark.asyncio
async def test_refresh_does_not_renotify_when_review_count_unchanged(monkeypatch):
    articles = [{"id": "a1", "status": "review", "title": "Old One",
                 "updated_at": "2026-07-18T00:00:00"}]
    monkeypatch.setattr(skeleton, "call_backend", _fake_call_backend(articles))
    ctx = _FakeCtx(initial_review_count=1)
    await skeleton.skeleton_refresh_overview(ctx)
    assert ctx.notified == []
