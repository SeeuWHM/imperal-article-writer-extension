"""Navigation handlers + content creation."""
from imperal_sdk import ActionResult
from imperal_sdk.types import ActionResult  # noqa: F811

from wpb_app import chat, save_ui_state, create_content as _create, get_content as _get_content, load_settings, update_content as _upd
from api_client import _post
from params import OpenEditorParams, CreateContentParams, SetEditorModeParams, EmptyParams, ImportFromWpParams
from response_models import NavStateResponse


@chat.function("go_plan", description="Switch main panel to Content Plan view.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_plan(ctx, params: EmptyParams) -> ActionResult:
    """Switch to Content Plan view."""
    await save_ui_state(ctx, {"active_view": "plan", "plan_filter": "all"})
    return ActionResult.success(data={}, summary="Switched to Content Plan")


@chat.function("go_plan_ideas", description="Switch to Content Plan showing only Idea status items.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_plan_ideas(ctx, params: EmptyParams) -> ActionResult:
    """Filter Content Plan to show only Idea items."""
    await save_ui_state(ctx, {"active_view": "plan", "plan_filter": "idea"})
    return ActionResult.success(data={}, summary="Plan: Ideas")


@chat.function("go_plan_writing", description="Switch to Content Plan showing only Writing status items.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_plan_writing(ctx, params: EmptyParams) -> ActionResult:
    """Filter Content Plan to show only Writing items."""
    await save_ui_state(ctx, {"active_view": "plan", "plan_filter": "writing"})
    return ActionResult.success(data={}, summary="Plan: Writing")


@chat.function("go_plan_review", description="Switch to Content Plan showing only Review status items.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_plan_review(ctx, params: EmptyParams) -> ActionResult:
    """Filter Content Plan to show only Review items."""
    await save_ui_state(ctx, {"active_view": "plan", "plan_filter": "review"})
    return ActionResult.success(data={}, summary="Plan: Review")


@chat.function("go_plan_done", description="Switch to Content Plan showing only Published/Done items.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_plan_done(ctx, params: EmptyParams) -> ActionResult:
    """Filter Content Plan to show only Published items."""
    await save_ui_state(ctx, {"active_view": "plan", "plan_filter": "published"})
    return ActionResult.success(data={}, summary="Plan: Done")


@chat.function("go_rankings", description="Switch main panel to Rankings view.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_rankings(ctx, params: EmptyParams) -> ActionResult:
    """Switch to Rankings view."""
    await save_ui_state(ctx, {"active_view": "rankings"})
    return ActionResult.success(data={}, summary="Switched to Rankings")


@chat.function("go_keywords", description="Switch main panel to Keyword Research view.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_keywords(ctx, params: EmptyParams) -> ActionResult:
    """Switch to Keyword Research view."""
    await save_ui_state(ctx, {"active_view": "keywords"})
    return ActionResult.success(data={}, summary="Switched to Keywords")


@chat.function("go_settings", description="Switch main panel to Settings view.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_settings(ctx, params: EmptyParams) -> ActionResult:
    """Switch to Settings view."""
    await save_ui_state(ctx, {"active_view": "settings"})
    return ActionResult.success(data={}, summary="Switched to Settings")


@chat.function("go_docs", description="Switch main panel to Knowledge Base (docs) view.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_docs(ctx, params: EmptyParams) -> ActionResult:
    """Switch to Knowledge Base view."""
    await save_ui_state(ctx, {"active_view": "docs"})
    return ActionResult.success(data={}, summary="Switched to Knowledge Base")


@chat.function(
    "open_editor",
    description="Open a specific content item in the editor.",
    action_type="read",
    event="seo.nav.changed",
    data_model=NavStateResponse,
)
async def open_editor(ctx, params: OpenEditorParams) -> ActionResult:
    """Open a content item in the editor by ID."""
    if not params.content_id:
        return ActionResult.error(error="Select an item from the dropdown first.")
    item = await _get_content(ctx, params.content_id)
    kw         = (item.get("keyword") or item.get("title") or params.content_id) if item else params.content_id
    word_count = len((item.get("content") or "").split()) if item else 0
    status     = item.get("status", "idea") if item else "unknown"
    wp_id      = item.get("wp_post_id", "") if item else ""
    await save_ui_state(ctx, {
        "active_view": "editor",
        "selected_id": params.content_id,
        "editor_mode": "edit",
        "last_opened_keyword": kw[:28],
    })
    return ActionResult.success(
        data={
            "content_id":       params.content_id,
            "keyword":          kw,
            "word_count":       word_count,
            "status":           status,
            "wp_post_id":       wp_id,
            "has_open_article": True,
        },
        summary=(
            f"Article open: '{kw}' ({word_count} words, {status}).\n"
            f"article_id={params.content_id}\n"
            f"You can now edit it — tell me what to change (перепиши, улучши, добавь...)."
        ),
    )


@chat.function(
    "set_editor_mode",
    description="Toggle editor between edit and preview mode.",
    action_type="read",
    event="seo.nav.changed",
    data_model=NavStateResponse,
)
async def set_editor_mode(ctx, params: SetEditorModeParams) -> ActionResult:
    """Set editor display mode to 'edit' or 'preview'."""
    await save_ui_state(ctx, {"editor_mode": params.mode})
    return ActionResult.success(data={}, summary=f"Editor mode: {params.mode}")


@chat.function("go_preview", description="Switch editor to preview mode.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_preview(ctx, params: EmptyParams) -> ActionResult:
    """Switch editor to preview mode."""
    await save_ui_state(ctx, {"editor_mode": "preview"})
    return ActionResult.success(data={}, summary="Preview mode")


@chat.function("go_edit", description="Switch editor to edit mode.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def go_edit(ctx, params: EmptyParams) -> ActionResult:
    """Switch editor to edit mode."""
    await save_ui_state(ctx, {"editor_mode": "edit"})
    return ActionResult.success(data={}, summary="Edit mode")


@chat.function("show_editor_panel", description="Show the article text editor in Step 3.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def show_editor_panel(ctx, params: EmptyParams) -> ActionResult:
    """Reveal the rich-text editor in Step 3."""
    await save_ui_state(ctx, {"show_editor": True})
    return ActionResult.success(data={}, summary="Editor shown")


@chat.function("hide_editor_panel", description="Hide the article text editor in Step 3.", action_type="read", event="seo.nav.changed", data_model=NavStateResponse)
async def hide_editor_panel(ctx, params: EmptyParams) -> ActionResult:
    """Hide the rich-text editor in Step 3."""
    await save_ui_state(ctx, {"show_editor": False})
    return ActionResult.success(data={}, summary="Editor hidden")


@chat.function(
    "resume_editor",
    description="Return to the editor for the currently open content item.",
    action_type="read",
    event="seo.nav.changed",
    data_model=NavStateResponse,
)
async def resume_editor(ctx, params: EmptyParams) -> ActionResult:
    """Return to the editor for the currently open article."""
    await save_ui_state(ctx, {"active_view": "editor"})
    return ActionResult.success(data={}, summary="Returned to editor")


@chat.function(
    "new_content",
    description="Create a new EMPTY content plan item (blog post or newsletter placeholder) and open it in the editor. Use ONLY for creating a blank placeholder — NOT for AI article writing (use ai_write for that).",
    action_type="write",
    chain_callable=True,
    effects=["create:content"],
    event="seo.content.created",
)
async def new_content(ctx, params: CreateContentParams) -> ActionResult:
    """Create a new content plan item and open it in the editor."""
    data = {
        "keyword": params.keyword,
        "type": params.type,
        "title": params.title or "",
        "content": "",
        "subject": "",
        "status": "idea",
        "volume": params.volume,
        "difficulty": params.difficulty,
        "wp_post_id": None,
        "ml_campaign_id": None,
    }
    item_id = await _create(ctx, data)
    await save_ui_state(ctx, {
        "active_view": "editor",
        "selected_id": item_id,
        "editor_mode": "edit",
    })
    return ActionResult.success(
        data={"id": item_id, "keyword": params.keyword},
        summary=f"Created '{params.keyword}' ({params.type}) and opened in editor", refresh_panels=["sidebar"],
    )


@chat.function(
    "import_from_wp",
    description=(
        "Import a WordPress post and optionally edit it in one step. "
        "Use when user mentions editing/rewriting a specific WordPress post. "
        "If instruction is provided (rewrite intro, add section, etc.), applies the edit immediately after import — NO second tool call needed. "
        "Use for: перепиши вступление поста 1902, edit WP post 1902, "
        "import and rewrite, import and improve, измени статью из WP. "
        "post_id: WP post ID. instruction: what to change (optional)."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:content"],
    event="seo.content.created",
)
async def import_from_wp(ctx, params: ImportFromWpParams) -> ActionResult:
    """Pull a WP post into Content Plan so Webbee can edit it."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")

    # Fetch post from WP via MOS
    data = await _post(ctx, "/api/wordpress/get", {
        "wp_url":      s["wp_url"],
        "wp_user":     s["wp_username"],
        "wp_password": s["wp_app_password"],
        "post_id":     params.post_id,
    }) if params.post_id else {}

    # If no post_id, search by keyword in recent posts
    if not data or "error" in data:
        posts_data = await _post(ctx, "/api/wordpress/list", {
            "wp_url":      s["wp_url"],
            "wp_user":     s["wp_username"],
            "wp_password": s["wp_app_password"],
            "per_page":    50,
            "status":      "any",
        })
        posts = posts_data.get("posts", []) if "error" not in posts_data else []
        q = (params.keyword_hint or "").lower()
        match = next(
            (p for p in posts if q in (p.get("title") or "").lower() or q in (p.get("slug") or "").lower()),
            None
        )
        if not match:
            titles = [p.get("title", "")[:40] for p in posts[:10]]
            return ActionResult.error(
                error=f"Post '{params.keyword_hint}' not found in WordPress. Available: {', '.join(titles)}"
            )
        # Fetch full content
        data = await _post(ctx, "/api/wordpress/get", {
            "wp_url":      s["wp_url"],
            "wp_user":     s["wp_username"],
            "wp_password": s["wp_app_password"],
            "post_id":     match["id"],
        })

    if "error" in data:
        return ActionResult.error(error=f"Failed to fetch post: {data['error']}")

    title   = data.get("title", "Imported post")
    content = data.get("content", "")
    slug    = data.get("slug", "")
    wp_id   = data.get("id")
    # keyword = slug → spaces
    keyword = slug.replace("-", " ") if slug else title[:40].lower()

    item_id = await _create(ctx, {
        "keyword":    keyword,
        "title":      title,
        "content":    content,
        "status":     "review",
        "type":       "blog",
        "wp_post_id": wp_id,
        "slug":       slug,
    })
    await save_ui_state(ctx, {"active_view": "editor", "selected_id": item_id, "editor_mode": "edit"})

    # If instruction provided, start async rewrite job
    if params.instruction and content:
        try:
            instruction = params.instruction + (f" Preserve keyword '{keyword}'." if keyword else "")
            job_data = await _post(ctx, "/api/content/refine/start", {
                "user_key": "", "content": content, "keyword": keyword, "instruction": instruction,
            }, timeout=10)
            job_id = job_data.get("job_id", "") if "error" not in job_data else ""
            if job_id:
                await save_ui_state(ctx, {"pending_wp_edit": str(wp_id), "pending_wp_edit_job": job_id})
                await _upd(ctx, item_id, {"job_id": job_id, "generating": True})
                return ActionResult.success(
                    data={"item_id": item_id, "wp_post_id": wp_id, "title": title, "job_id": job_id},
                    summary=(
                        f"✅ Imported '{title}' (WP #{wp_id}). Rewrite started.\n"
                        f"Job ID: {job_id}\n"
                        f"Call check_article_job in ~60-90 seconds — it will save changes to WordPress automatically."
                    ),
                )
        except Exception:
            pass  # Fall through to plain import result if edit fails

    return ActionResult.success(
        data={"item_id": item_id, "content_id": item_id, "wp_post_id": wp_id, "title": title},
        summary=(
            f"✅ Imported '{title}' (WP #{wp_id}) into Content Plan. item_id={item_id}\n"
            f"Article is now in Review status and open in editor.\n"
            f"You can now edit it — use patch_article or improve_article with item_id={item_id}."
        ),
    )
