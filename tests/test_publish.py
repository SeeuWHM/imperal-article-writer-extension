"""Tests for publish handlers — WP error paths and settings."""
import pytest
from imperal_sdk.testing import MockContext

import handlers_nav
import handlers_publish
from handlers_publish import _pick_category, _prepare_content

_FAKE_PW = "fake-test-pw"        # nosec — not a real credential
_FAKE_KEY = "dummy-sr-token"  # nosec — not a real credential


@pytest.fixture
def ctx():
    return MockContext(role="admin")


async def test_publish_wp_no_key(ctx):
    """Returns error when WP app password not configured."""
    create_result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="test article", type="blog",
    ))
    content_id = create_result.data["id"]

    result = await handlers_publish.publish_wp(ctx, handlers_publish.PublishWpParams(
        content_id=content_id,
        status="draft",
    ))
    assert result.status == "error"
    assert "Application Password" in result.error


async def test_publish_wp_empty_content(ctx):
    """Returns error when content body is empty."""
    await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        wp_app_password=_FAKE_PW,
    ))
    create_result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="empty article", type="blog",
    ))
    content_id = create_result.data["id"]

    result = await handlers_publish.publish_wp(ctx, handlers_publish.PublishWpParams(
        content_id=content_id,
        status="draft",
    ))
    assert result.status == "error"
    assert "empty" in result.error.lower()


async def test_publish_wp_missing_item(ctx):
    """Returns error when content ID does not exist."""
    await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        wp_app_password=_FAKE_PW,
    ))
    result = await handlers_publish.publish_wp(ctx, handlers_publish.PublishWpParams(
        content_id="nonexistent_id",
        status="draft",
    ))
    assert result.status == "error"
    assert "not found" in result.error.lower()


async def test_save_settings(ctx):
    result = await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        seranking_api_key=_FAKE_KEY,
        wp_app_password=_FAKE_PW,
    ))
    assert result.status == "success"

    page = await ctx.store.query("seo_settings", limit=1)
    s = page.data[0].data
    assert s["seranking_api_key"] == _FAKE_KEY
    assert s["wp_app_password"] == _FAKE_PW


def test_pick_category_by_type():
    assert _pick_category("cloud hosting", "comparison") == 21
    assert _pick_category("namecheap review", "review") == 21
    assert _pick_category("linux news", "news") == 51
    assert _pick_category("how to install php", "tutorial") == 45
    assert _pick_category("best hosting", "blog") == 45
    assert _pick_category("ultimate guide to vps", "pillar") == 48


def test_pick_category_by_keyword():
    assert _pick_category("wordpress hosting", "blog") == 46
    assert _pick_category("webhostmost review", "review") == 47
    assert _pick_category("wpanel guide", "blog") == 47
    assert _pick_category("webbee ai assistant", "blog") == 47


def test_prepare_content_replaces_internal_links():
    html = '<p>See <a href="[INTERNAL]">best hosting</a> for details.</p>'
    result = _prepare_content(html, "", "https://blog.webhostmost.com")
    assert "[INTERNAL]" not in result
    assert 'href="https://blog.webhostmost.com"' in result


def test_prepare_content_fallback_no_blog_url():
    html = '<a href="[INTERNAL]">link</a>'
    result = _prepare_content(html, "", "")
    assert 'href="#"' in result


def test_prepare_content_appends_faq_schema():
    html = "<p>Article body</p>"
    schema = '<script type="application/ld+json">{"@type":"FAQPage"}</script>'
    result = _prepare_content(html, schema, "")
    assert result.endswith(schema)
    assert "Article body" in result


def test_prepare_content_no_schema():
    html = "<p>Body</p>"
    result = _prepare_content(html, "", "")
    assert result == html


async def test_save_settings_partial_update(ctx):
    """Partial update merges with existing settings."""
    await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        seranking_api_key="key_one",  # nosec
    ))
    await handlers_publish.save_settings_fn(ctx, handlers_publish.SaveSettingsParams(
        wp_app_password="pw_two",  # nosec
    ))

    page = await ctx.store.query("seo_settings", limit=1)
    s = page.data[0].data
    assert s["seranking_api_key"] == "key_one"  # nosec
    assert s["wp_app_password"] == "pw_two"  # nosec
