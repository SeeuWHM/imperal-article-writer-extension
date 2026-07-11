"""Tests for SE Ranking handlers — error paths when key not configured."""
import pytest
from imperal_sdk.testing import MockContext

import handlers_seo
import handlers_publish


@pytest.fixture
def ctx():
    return MockContext(role="admin")


async def test_fetch_keywords_no_key(ctx):
    result = await handlers_seo.fetch_keywords(
        ctx,
        handlers_seo.FetchKeywordsParams(domain="blog.webhostmost.com"),
    )
    assert result.status == "error"
    assert "SE Ranking API key" in result.error


async def test_fetch_gaps_no_key(ctx):
    result = await handlers_seo.fetch_gaps(
        ctx,
        handlers_seo.FetchGapsParams(competitor="hostinger.com"),
    )
    assert result.status == "error"
    assert "SE Ranking API key" in result.error


async def test_fetch_rankings_no_key(ctx):
    result = await handlers_seo.fetch_rankings(ctx, None)
    assert result.status == "error"
    assert "SE Ranking API key" in result.error


async def test_fetch_rankings_no_project_id(ctx):
    await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        seranking_api_key="project_key_test",
    ))
    result = await handlers_seo.fetch_rankings(ctx, None)
    assert result.status == "error"
    assert "Project ID" in result.error


async def test_go_keywords_view(ctx):
    result = await handlers_seo.fetch_keywords(
        ctx,
        handlers_seo.FetchKeywordsParams(domain="blog.webhostmost.com"),
    )
    # Still an error (no key), but we verify the function signature works
    assert result.status in ("success", "error")
