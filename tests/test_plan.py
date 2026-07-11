"""Tests for content plan CRUD and navigation handlers."""
import pytest
from imperal_sdk.testing import MockContext

import handlers_nav
import handlers_content


@pytest.fixture
def ctx():
    return MockContext(role="admin")


async def test_new_content_creates_and_opens(ctx):
    result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="best web hosting 2026",
        type="blog",
        volume=2400,
        difficulty=35,
    ))
    assert result.status == "success"
    assert result.data["keyword"] == "best web hosting 2026"
    content_id = result.data["id"]

    state_page = await ctx.store.query("seo_ui_state", limit=1)
    state = state_page.data[0].data
    assert state["active_view"] == "editor"
    assert state["selected_id"] == content_id


async def test_go_plan_switches_view(ctx):
    await handlers_nav.go_plan(ctx, None)
    state_page = await ctx.store.query("seo_ui_state", limit=1)
    state = state_page.data[0].data
    assert state["active_view"] == "plan"


async def test_save_draft(ctx):
    create_result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="web hosting guide",
        type="blog",
    ))
    content_id = create_result.data["id"]

    result = await handlers_content.save_draft(ctx, handlers_content.SaveDraftParams(
        content_id=content_id,
        title="The Complete Web Hosting Guide 2026",
        content="<h2>Introduction</h2><p>Web hosting is...</p>",
    ))
    assert result.status == "success"
    # Storage is MOS-backed in production; ctx.store not checked here


async def test_update_status(ctx):
    create_result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="newsletter topic",
        type="newsletter",
    ))
    content_id = create_result.data["id"]

    result = await handlers_content.update_status(ctx, handlers_content.UpdateStatusParams(
        content_id=content_id,
        status="review",
    ))
    assert result.status == "success"
    assert result.data["status"] == "review"


async def test_update_status_invalid(ctx):
    create_result = await handlers_nav.new_content(ctx, handlers_nav.CreateContentParams(
        keyword="test", type="blog",
    ))
    content_id = create_result.data["id"]

    result = await handlers_content.update_status(ctx, handlers_content.UpdateStatusParams(
        content_id=content_id,
        status="invalid_status",
    ))
    assert result.status == "error"


async def test_set_editor_mode(ctx):
    await handlers_nav.set_editor_mode(ctx, handlers_nav.SetEditorModeParams(mode="preview"))
    state_page = await ctx.store.query("seo_ui_state", limit=1)
    state = state_page.data[0].data
    assert state["editor_mode"] == "preview"
