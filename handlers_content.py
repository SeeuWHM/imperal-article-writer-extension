"""Content CRUD handlers (save/update/delete/brief). AI writing moved to handlers_ai_write.py."""
import time

from imperal_sdk import ActionResult, ui
from imperal_sdk.types import ActionResult  # noqa: F811

from wpb_app import chat, get_content, update_content, delete_content, load_settings, load_ui_state, list_content, create_content, _store_list
from api_client import generate_brief as _mos_brief, log_action, _post, start_refine_article
from params import SaveDraftParams, UpdateStatusParams, DeleteContentParams, AiBriefParams, SaveBriefParams, PatchArticleParams, EmptyParams


async def _resolve_id(ctx, content_id: str, keyword_hint: str = "") -> str:
    """Return content_id → ctx.prior → ui_state selected_id → keyword search → most recent."""
    if content_id:
        return content_id
    # Check chain prior step — import_from_wp or open_editor may have set item_id
    try:
        for step_name in ("import_from_wp", "open_editor", "new_content"):
            prior = getattr(getattr(ctx, "prior", None), step_name, None)
            if prior:
                for field in ("item_id", "content_id", "id"):
                    val = getattr(prior, field, None)
                    if val:
                        return str(val)
    except Exception:
        pass
    # Check ui_state (set when article is opened in editor)
    state = await load_ui_state(ctx)
    if state.get("selected_id"):
        return state["selected_id"]
    # Search by keyword_hint or WP post ID
    if keyword_hint:
        items = await list_content(ctx)
        q = keyword_hint.lower().strip()
        # WP post ID numeric match
        if q.isdigit():
            found = next((i for i in items if str(i.get("wp_post_id", "")) == q), None)
            if found:
                return found["id"]
        # keyword/title match
        for item in items:
            kw    = (item.get("keyword") or "").lower()
            title = (item.get("title") or "").lower()
            if q in kw or q in title or any(w in kw or w in title for w in q.split() if len(w) > 3):
                return item["id"]
    # Fallback: most recently updated article (best guess)
    items = await list_content(ctx)
    if items:
        by_status = sorted(items, key=lambda x: {"review": 0, "writing": 1, "published": 2, "idea": 3}.get(x.get("status","idea"), 3))
        return by_status[0]["id"]
    return ""


@chat.function(
    "save_draft",
    description="Save title and HTML content from the editor to the content store.",
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def save_draft(ctx, params: SaveDraftParams) -> ActionResult:
    """Save title and HTML content from the editor."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            await log_action(ctx, "save_draft", cid, int((time.monotonic() - t0) * 1000), False, "Content item not found")
            return ActionResult.error(error="Content item not found")
        updates = {}
        if params.title:   updates["title"]   = params.title
        if params.content: updates["content"] = params.content
        if params.subject: updates["subject"] = params.subject
        if updates:
            await update_content(ctx, cid, updates)
        await log_action(ctx, "save_draft", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(data={"id": cid}, summary=f"Draft saved: {params.title or item.get('title', '...')}", refresh_panels=["sidebar"])
    except Exception as e:
        await log_action(ctx, "save_draft", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "update_status",
    description="Move a content item to a new status: idea, writing, review, or published.",
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def update_status(ctx, params: UpdateStatusParams) -> ActionResult:
    """Update the status of a content item."""
    valid = {"idea", "writing", "review", "published"}
    if params.status not in valid:
        return ActionResult.error(error=f"Invalid status '{params.status}'. Use: {', '.join(valid)}")
    cid = await _resolve_id(ctx, params.content_id)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="Content item not found")
    await update_content(ctx, cid, {"status": params.status})
    return ActionResult.success(data={"id": cid, "status": params.status}, summary=f"Status → {params.status}: {item.get('keyword', '')}", refresh_panels=["sidebar"])


@chat.function(
    "delete_content",
    description="Delete a content plan item permanently.",
    action_type="write",
    chain_callable=True,
    effects=["delete:content"],
    event="seo.content.updated",
)
async def delete_content_fn(ctx, params: DeleteContentParams) -> ActionResult:
    """Permanently delete a content item."""
    item = await get_content(ctx, params.content_id)
    if not item:
        return ActionResult.error(error="Content item not found")
    await delete_content(ctx, params.content_id)
    return ActionResult.success(data={"id": params.content_id}, summary=f"Deleted: {item.get('keyword', params.content_id)}", refresh_panels=["sidebar", "editor"])


@chat.function(
    "generate_brief",
    description="Generate an SEO content brief: title, meta description, H2/H3 outline, search intent. Saved and shown in the editor.",
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def generate_brief(ctx, params: AiBriefParams) -> ActionResult:
    """Generate an SEO content brief via MOS AI."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            await log_action(ctx, "generate_brief", cid, int((time.monotonic() - t0) * 1000), False, "Content item not found")
            return ActionResult.error(error="Content item not found")

        kw           = item.get("keyword", "")
        content_type = item.get("type", "blog")
        vol          = item.get("volume", 0)
        diff         = item.get("difficulty", 0)
        s            = await load_settings(ctx)
        language     = s.get("language", "en")

        data = await _mos_brief(ctx, keyword=kw, content_type=content_type,
                                volume=vol, difficulty=diff,
                                extra=params.extra or "", language=language)
        if "error" in data:
            await log_action(ctx, "generate_brief", cid, int((time.monotonic() - t0) * 1000), False, data["error"])
            return ActionResult.error(error=data["error"])

        brief_text = data.get("brief", "")
        await update_content(ctx, cid, {"brief": brief_text, "status": "writing"})
        await log_action(ctx, "generate_brief", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"brief": brief_text[:300]},
            summary=f"Brief ready for '{kw}' — visible in Step 1 of the editor.",
        )
    except Exception as e:
        await log_action(ctx, "generate_brief", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "save_brief",
    description="Save manually edited brief text.",
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def save_brief(ctx, params: SaveBriefParams) -> ActionResult:
    """Save edited brief text."""
    cid = await _resolve_id(ctx, params.content_id)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="Content item not found")
    await update_content(ctx, cid, {"brief": params.brief_text})
    return ActionResult.success(data={"id": cid}, summary="Brief saved.", refresh_panels=["sidebar"])


@chat.function(
    "patch_article",
    description=(
        "Edit or rewrite a specific part of an article. "
        "CALL THIS DIRECTLY — do NOT navigate to content plan first. "
        "Use keyword_hint to find the article by name if none is open. "
        "Use when user says: rewrite intro/paragraph/conclusion, fix this section, "
        "make it more engaging, перепиши абзац/вступление/заключение, "
        "сделай цепляющим, улучши начало, измени этот раздел, "
        "перепиши статью про X, add a section about X. "
        "keyword_hint: article name/keyword (e.g. 'infinityfree', 'affordable hosting'). "
        "Can work without an open article — just provide keyword_hint."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def patch_article(ctx, params: PatchArticleParams) -> ActionResult:
    """Apply a specific edit to the article content via AI on MOS server."""
    kw_hint = getattr(params, "keyword_hint", "")
    cid = await _resolve_id(ctx, params.content_id, kw_hint)
    item = await get_content(ctx, cid)

    # Last resort: if keyword_hint is a WP post ID, fetch directly from WP
    if not item and (params.content_id.isdigit() or kw_hint.isdigit()):
        wp_id_str = params.content_id if params.content_id.isdigit() else kw_hint
        s = await load_settings(ctx)
        if s.get("wp_app_password"):
            try:
                wp_data = await _post(ctx, "/api/wordpress/get", {
                    "wp_url": s["wp_url"], "wp_user": s["wp_username"],
                    "wp_password": s["wp_app_password"], "post_id": int(wp_id_str),
                })
                if "error" not in wp_data and wp_data.get("content"):
                    # Synthesize an item from WP data and patch directly
                    kw = wp_data.get("title", "")
                    content = wp_data.get("content", "")
                    data = await _post(ctx, "/api/content/refine", {
                        "content": content, "keyword": kw,
                        "instruction": params.instruction + (f" PRESERVE keyword '{kw}'." if kw else ""),
                    }, timeout=90)
                    new_content = data.get("content", "")
                    if new_content:
                        await _post(ctx, "/api/wordpress/update", {
                            "wp_url": s["wp_url"], "wp_user": s["wp_username"],
                            "wp_password": s["wp_app_password"],
                            "post_id": int(wp_id_str), "content": new_content,
                        })
                        return ActionResult.success(
                            data={"wp_post_id": wp_id_str},
                            summary=f"✅ WP post #{wp_id_str} updated — intro rewritten successfully.",
                        )
            except Exception:
                pass

    if not item:
        return ActionResult.error(error="Article not found. Try: specify WP post ID as keyword_hint, or open article from Content Plan.")

    content = item.get("content", "")
    # If no local content but WP post exists, fetch from WordPress
    if not content and item.get("wp_post_id"):
        s = await load_settings(ctx)
        if s.get("wp_app_password"):
            try:
                wp = await _post(ctx, "/api/wordpress/get", {
                    "wp_url": s["wp_url"], "wp_user": s["wp_username"],
                    "wp_password": s["wp_app_password"],
                    "post_id": int(item["wp_post_id"]),
                })
                content = wp.get("content", "")
                if content:
                    await update_content(ctx, cid, {"content": content})
            except Exception:
                pass
    if not content:
        return ActionResult.error(error="Article has no content. Run ai_write first, or publish it to WordPress.")

    kw = item.get("keyword", "")
    # Add keyword preservation to any patch instruction
    kw_note = (f" IMPORTANT: Preserve the focus keyword '{kw}' — it must remain in the first sentence "
               f"and appear throughout the text. Do not replace '{kw}' with synonyms.") if kw else ""
    instruction = params.instruction + kw_note

    # Save content_id for check_article_job to find after async job completes
    await save_ui_state(ctx, {"selected_id": cid, "active_view": "editor"})

    # Use async job — ctx.http timeout < AI generation time (30s vs 60-90s)
    job_data = await start_refine_article(ctx, content, kw, instruction)

    if "error" in job_data:
        return ActionResult.error(error=job_data["error"])

    job_id = job_data.get("job_id", "")
    return ActionResult.success(
        data={"job_id": job_id, "content_id": cid, "instruction": params.instruction[:80]},
        summary=(
            f"✏️ Rewrite started: '{params.instruction[:60]}'\n"
            f"Job ID: {job_id}\n"
            f"Takes ~60-90 seconds. Call check_article_job to get the result."
        ),
    )


@chat.function(
    "check_article_quality",
    description=(
        "Script-based article quality audit — zero AI tokens. "
        "Checks: word count, H2/H3 structure, comparison table, FAQ, outbound links, "
        "keyword density, em dashes, placeholders, bold text, lists. "
        "Returns score 0-100 and specific issues to fix."
    ),
    action_type="read",
    event="",
)
async def check_article_quality(ctx, params: AiBriefParams) -> ActionResult:
    """Script-only quality check using regex + HTML parsing on MOS server."""
    from imperal_sdk import ui
    cid = await _resolve_id(ctx, params.content_id)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="No article open.")

    content = item.get("content", "")
    if not content:
        return ActionResult.error(error="Article has no content. Run ai_write first.")

    data = await _post(ctx, "/api/content/quality_check", {
        "content":  content,
        "keyword":  item.get("keyword", ""),
        "title":    item.get("title", ""),
        "language": "en",
    }, timeout=10)

    if "error" in data:
        return ActionResult.error(error=data["error"])

    score  = data.get("score", 0)
    grade  = data.get("grade", "?")
    stats  = data.get("stats", {})
    issues = data.get("issues", [])

    fails  = [i for i in issues if i["level"] == "fail"]
    warns  = [i for i in issues if i["level"] == "warn"]

    summary_lines = [
        f"Quality score: {score}/100 (Grade {grade})",
        f"Words: {stats.get('word_count',0)} | H2: {stats.get('h2_count',0)} | Tables: {stats.get('table_count',0)} | Outbound links: {stats.get('outbound_links',0)}",
        f"Keyword density: {stats.get('kw_density',0)}% | FAQ: {'✓' if stats.get('faq') else '✗'} | Em dash: {'✗ FOUND' if stats.get('has_em_dash') else '✓ clean'}",
    ]
    if fails:
        summary_lines.append(f"\n🔴 {len(fails)} critical issues:")
        summary_lines.extend(f"  • {i['message']}" for i in fails)
    if warns:
        summary_lines.append(f"\n🟡 {len(warns)} warnings:")
        summary_lines.extend(f"  • {i['message']}" for i in warns)
    if not issues:
        summary_lines.append("✅ No issues found!")

    return ActionResult.success(data=data, summary="\n".join(summary_lines))


@chat.function(
    "list_articles",
    description=(
        "List all content items in the content plan (articles, newsletters). "
        "Use when user asks: show my articles, what articles do I have, list content, "
        "show drafts, what have I written, articles from another device."
    ),
    action_type="read",
)
async def list_articles(ctx, params: EmptyParams) -> ActionResult:
    """Show all content items from MOS storage for this user."""
    items = await list_content(ctx)

    if not items:
        return ActionResult.success(
            data={"items": [], "count": 0},
            summary="No articles in content plan yet. Use 'Build Content Plan (AI)' or '+ New item' to add some.",
        )

    STATUS_ORDER = {"review": 0, "writing": 1, "published": 2, "idea": 3}
    items_sorted = sorted(items, key=lambda x: STATUS_ORDER.get(x.get("status", "idea"), 3))

    rows = [
        {
            "keyword": (i.get("keyword") or i.get("title") or "untitled")[:45],
            "type":    i.get("type", "blog"),
            "status":  i.get("status", "idea"),
            "words":   str(len((i.get("content") or "").split())) if i.get("content") else "—",
            "wp":      "✓" if i.get("wp_post_id") else "—",
            "id":      i.get("id", ""),
        }
        for i in items_sorted
    ]

    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="keyword", label="Keyword / Topic", width="40%"),
            ui.DataColumn(key="type",    label="Type",            width="12%"),
            ui.DataColumn(key="status",  label="Status",          width="12%"),
            ui.DataColumn(key="words",   label="Words",           width="10%"),
            ui.DataColumn(key="wp",      label="In WP",           width="8%"),
            ui.DataColumn(key="id",      label="ID",              width="18%"),
        ],
        rows=rows,
    )

    published = sum(1 for i in items if i.get("status") == "published")
    writing   = sum(1 for i in items if i.get("status") == "writing")
    review    = sum(1 for i in items if i.get("status") == "review")
    in_wp     = sum(1 for i in items if i.get("wp_post_id"))

    summary = (
        f"{len(items)} content items: {published} published, {review} in review, "
        f"{writing} writing, {in_wp} synced to WordPress.\n"
        "To open an item in the editor, say its keyword or ID."
    )
    return ActionResult.success(data={"items": items, "count": len(items)}, summary=summary, ui=table)


@chat.function(
    "migrate_from_store",
    description=(
        "Migrate content items from old ctx.store to MOS server storage. "
        "One-time migration — use if articles are missing after storage upgrade."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.created",
)
async def migrate_from_store(ctx, params: EmptyParams) -> ActionResult:
    """Read legacy ctx.store content items and import to MOS SQLite."""
    CONTENT_COL = "seo_content"
    try:
        page = await ctx.store.query(CONTENT_COL, limit=200)
    except Exception as e:
        return ActionResult.error(error=f"Could not read ctx.store: {e}")

    docs = getattr(page, "data", None) or []
    if not docs:
        return ActionResult.success(
            data={"migrated": 0},
            summary="No items found in old storage. Nothing to migrate.",
        )

    migrated = 0
    skipped  = 0
    for d in docs:
        if not isinstance(getattr(d, "data", None), dict):
            continue
        item = dict(d.data)
        item.pop("id", None)  # MOS will assign new UUID
        try:
            await create_content(ctx, item)
            migrated += 1
        except Exception:
            skipped += 1

    return ActionResult.success(
        data={"migrated": migrated, "skipped": skipped},
        summary=f"Migration complete: {migrated} items imported to MOS storage. {skipped} skipped.",
    )


@chat.function(
    "show_article",
    description=(
        "Show the full article text in chat. "
        "ALWAYS USE for: покажи статью, отправь статью, покажи текст статьи, "
        "show article, send article, покажи полный текст, отправь мне статью, "
        "покажи что написано, покажи содержимое статьи, вывести статью в чат."
    ),
    action_type="read",
)
async def show_article(ctx, params: EmptyParams) -> ActionResult:
    """Return full article text in chat so user can copy/review it."""
    import re
    cid = await _resolve_id(ctx, "")
    if not cid:
        return ActionResult.error(error="No article open. Open or create an article first.")
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error=f"Article {cid} not found.")

    html = item.get("content", "")
    title = item.get("title") or item.get("keyword", "Untitled")
    kw = item.get("keyword", "")
    word_count = item.get("word_count") or len(html.split())

    # Strip HTML tags for readable plain text
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Truncate if too long (keep first ~8000 chars)
    truncated = ""
    if len(text) > 8000:
        text = text[:8000]
        truncated = f"\n\n[... truncated — full article has ~{word_count} words, open editor to see complete text]"

    summary = f"# {title}\n**Keyword:** {kw}\n**Words:** {word_count}\n\n{text}{truncated}"
    return ActionResult.success(
        data={"title": title, "keyword": kw, "word_count": word_count},
        summary=summary,
    )
