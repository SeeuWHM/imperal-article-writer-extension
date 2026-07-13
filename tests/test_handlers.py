"""Unit tests — no network. MockContext + monkeypatched call_backend.

Mirrors matomo-analytics-extension/tests/test_handlers.py's convention:
patch `call_backend` on the HANDLER module (where it's imported and used),
never on api_client (where it's merely defined) — patching the wrong one
lets the real function run and hit the network during tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_projects
import handlers_articles
import handlers_generate
import api_client
from params import (
    CreateProjectParams, UpdateProjectContextParams, ProjectIdParams,
    CreateArticleParams, ListArticlesParams, ArticleIdParams,
    UpdateArticleStatusParams, SaveArticleSectionParams,
    GenerateArticleParams, GenerationJobStatusParams, PatchArticleParams,
)
from response_models import DeletedResponse


class _EmptyParams:
    """Matches the handler modules' own local _EmptyParams — no fields."""


def _ctx(configured: bool = True) -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"backend_jwt": "test-jwt"} if configured else {})
    return ctx


# ─── projects ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/projects"
        assert kw["json"]["name"] == "My Site"
        return {"id": "p1", "name": "My Site", "keywords": ["a", "b"]}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_project(_ctx(), CreateProjectParams(name="My Site", keywords=["a", "b"]))
    assert result.status == "success"
    assert result.data.id == "p1"
    assert result.data.keywords == ["a", "b"]


@pytest.mark.asyncio
async def test_create_project_backend_error(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return {"error": "Article Writer backend is not configured on our side yet — this has been logged.", "_config": True}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_project(_ctx(), CreateProjectParams(name="X"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_list_projects_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "GET" and path == "/v1/projects"
        return {"data": [{"id": "p1", "name": "Site A"}, {"id": "p2", "name": "Site B"}]}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_list_projects(_ctx(), handlers_projects._EmptyParams())
    assert result.status == "success"
    assert result.data.count == 2
    assert [p.name for p in result.data.projects] == ["Site A", "Site B"]


@pytest.mark.asyncio
async def test_update_project_context_requires_a_field():
    result = await handlers_projects.fn_update_project_context(
        _ctx(), UpdateProjectContextParams(project_id="p1"),
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_update_project_context_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/projects/p1/context"
        assert kw["json"] == {"brand_voice": "punchy"}
        return {"id": "p1", "name": "Site A", "brand_voice": "punchy"}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_update_project_context(
        _ctx(), UpdateProjectContextParams(project_id="p1", brand_voice="punchy"),
    )
    assert result.status == "success"
    assert result.data.brand_voice == "punchy"


@pytest.mark.asyncio
async def test_delete_project_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE" and path == "/v1/projects/p1"
        return {}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_delete_project(_ctx(), ProjectIdParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.deleted is True


# ─── articles ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_article_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/articles"
        return {"id": "a1", "project_id": "p1", "title": "Hello", "status": "idea", "word_count": 0}

    monkeypatch.setattr(handlers_articles, "call_backend", fake_call)
    result = await handlers_articles.fn_create_article(_ctx(), CreateArticleParams(project_id="p1", title="Hello"))
    assert result.status == "success"
    assert result.data.status == "idea"


@pytest.mark.asyncio
async def test_list_articles_never_carries_body(monkeypatch):
    """Structural guarantee: even if the backend somehow returned a `content`
    field, ArticleSummary has no such field to receive it into."""
    async def fake_call(ctx, method, path, **kw):
        assert kw["params"]["project_id"] == "p1"
        return {"data": [
            {"id": "a1", "project_id": "p1", "title": "T", "status": "review",
             "word_count": 650, "seo_score": {"flags": ["short"]}, "content": "SHOULD NOT LEAK"},
        ]}

    monkeypatch.setattr(handlers_articles, "call_backend", fake_call)
    result = await handlers_articles.fn_list_articles(_ctx(), ListArticlesParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.count == 1
    a = result.data.articles[0]
    assert a.seo_flags == ["short"]
    assert not hasattr(a, "content")
    assert "content" not in a.model_dump()


@pytest.mark.asyncio
async def test_update_article_status_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/articles/a1"
        assert kw["json"] == {"status": "published"}
        return {"id": "a1", "project_id": "p1", "status": "published", "word_count": 650}

    monkeypatch.setattr(handlers_articles, "call_backend", fake_call)
    result = await handlers_articles.fn_update_article_status(
        _ctx(), UpdateArticleStatusParams(article_id="a1", status="published"),
    )
    assert result.status == "success"
    assert result.data.status == "published"


@pytest.mark.asyncio
async def test_save_article_section_requires_a_field():
    result = await handlers_articles.fn_save_article_section(
        _ctx(), SaveArticleSectionParams(article_id="a1", order_index=0),
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_save_article_section_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/articles/a1/sections/0"
        assert kw["json"] == {"content": "New text"}
        return {}

    monkeypatch.setattr(handlers_articles, "call_backend", fake_call)
    result = await handlers_articles.fn_save_article_section(
        _ctx(), SaveArticleSectionParams(article_id="a1", order_index=0, content="New text"),
    )
    assert result.status == "success"


@pytest.mark.asyncio
async def test_delete_article_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE" and path == "/v1/articles/a1"
        return {}

    monkeypatch.setattr(handlers_articles, "call_backend", fake_call)
    result = await handlers_articles.fn_delete_article(_ctx(), ArticleIdParams(article_id="a1"))
    assert result.status == "success"


# ─── generation / patch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_article_returns_job(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/articles/a1/generate"
        assert kw["json"]["brief"] == "Write about CDNs"
        return {"id": "job1", "status": "queued"}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_generate_article(
        _ctx(), GenerateArticleParams(article_id="a1", brief="Write about CDNs"),
    )
    assert result.status == "success"
    assert result.data.job_id == "job1"
    assert result.data.article_id == "a1"


@pytest.mark.asyncio
async def test_check_generation_status_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert path == "/v1/articles/a1/jobs/job1"
        return {"id": "job1", "status": "done", "model": "claude-sonnet-5", "tokens_used": 4000}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_check_generation_status(
        _ctx(), GenerationJobStatusParams(article_id="a1", job_id="job1"),
    )
    assert result.status == "success"
    assert result.data.status == "done"
    assert result.data.tokens_used == 4000


@pytest.mark.asyncio
async def test_patch_article_returns_preview_not_full_body(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/articles/a1/patch"
        assert kw["json"]["instruction"] == "make it punchier"
        return {
            "section_id": "sec1", "order_index": 0, "heading": "Intro",
            "preview": "short preview…", "seo_score": {"word_count": 660, "flags": []},
        }

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_patch_article(
        _ctx(), PatchArticleParams(article_id="a1", instruction="make it punchier"),
    )
    assert result.status == "success"
    assert result.data.preview == "short preview…"
    assert "content" not in result.data.model_dump()
    assert "sections" not in result.data.model_dump()


# ─── api_client — config guard ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_backend_reports_missing_jwt():
    data = await api_client.call_backend(_ctx(configured=False), "GET", "/v1/projects")
    assert data["_config"] is True
    assert "error" in data
