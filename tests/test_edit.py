"""Unit tests for Webbee's full-text read + edit (handlers_edit.py)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_edit
from params import ArticleIdParams, EditFullArticleParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"backend_jwt": "test-jwt"})
    return ctx


@pytest.mark.asyncio
async def test_read_full_article_returns_markdown(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "GET" and path == "/v1/articles/a1"
        return {"id": "a1", "title": "Best hosting", "status": "review", "word_count": 900,
                "sections": [{"heading": "Intro", "content": "Opening **line**."}]}

    monkeypatch.setattr(handlers_edit, "call_backend", fake_call)
    result = await handlers_edit.fn_read_full_article(_ctx(), ArticleIdParams(article_id="a1"))
    assert result.status == "success"
    assert result.data.markdown.startswith("# Best hosting")
    assert "## Intro" in result.data.markdown
    assert "Opening **line**." in result.data.markdown


@pytest.mark.asyncio
async def test_edit_full_article_persists_title_and_body(monkeypatch):
    captured = {}

    async def fake_call(ctx, method, path, **kw):
        if method == "PUT" and path == "/v1/articles/a1/sections":
            captured["sections"] = kw["json"]["sections"]
            return {"id": "a1", "project_id": "p1", "status": "review", "word_count": 5}
        if method == "PATCH" and path == "/v1/articles/a1/meta":
            captured["title"] = kw["json"]["title"]
            return {"id": "a1", "project_id": "p1", "title": kw["json"]["title"], "status": "review", "word_count": 5}
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(handlers_edit, "call_backend", fake_call)
    md = "# New Title\n\n## Intro\n\nEdited **body**.\n\n## More\n\nSecond section."
    result = await handlers_edit.fn_edit_full_article(
        _ctx(), EditFullArticleParams(article_id="a1", content_markdown=md)
    )
    assert result.status == "success"
    assert captured["title"] == "New Title"
    assert [s["heading"] for s in captured["sections"]] == ["Intro", "More"]
    assert "Edited **body**." in captured["sections"][0]["content"]
    assert not hasattr(result.data, "sections")


@pytest.mark.asyncio
async def test_edit_full_article_rejects_empty(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        raise AssertionError("should not call backend for empty text")

    monkeypatch.setattr(handlers_edit, "call_backend", fake_call)
    result = await handlers_edit.fn_edit_full_article(
        _ctx(), EditFullArticleParams(article_id="a1", content_markdown="   ")
    )
    assert result.status == "error"
