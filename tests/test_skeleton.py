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
