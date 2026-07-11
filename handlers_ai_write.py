"""AI article writing handlers — background generation with auto-delivery."""
import asyncio
import time

from imperal_sdk import ActionResult

from wpb_app import chat, get_content, update_content, load_settings, save_ui_state, load_ui_state
from api_client import (keywords_for_article, start_generate_article,
                        poll_article_job, generate_newsletter_mos as _mos_newsletter,
                        log_action, _post)
from handlers_content import _resolve_id
from handlers_docs import build_docs_context
from params import AiWriteParams, AiBriefParams


async def _save_job_result(ctx, cid: str, item: dict, data: dict) -> tuple[dict, bool]:
    """Save completed job result to content store. Returns (updates_dict, wp_saved)."""
    result     = data.get("result", {})
    draft_html = result.get("content", "")
    final_title = result.get("title", "")
    meta_desc  = result.get("meta_description", "")
    faq_schema = result.get("faq_schema", "")

    updates: dict = {"content": draft_html, "status": "review", "generating": False, "job_id": None}
    if meta_desc:  updates["meta_description"] = meta_desc
    if faq_schema: updates["faq_schema"]        = faq_schema
    if final_title and final_title != item.get("keyword", ""):
        updates["title"] = final_title

    await update_content(ctx, cid, updates)

    # Patch WP post if this job was triggered by edit_wp_article / import_from_wp
    wp_saved = False
    ui_state = await load_ui_state(ctx)
    pending_wp  = ui_state.get("pending_wp_edit", "")
    pending_job = ui_state.get("pending_wp_edit_job", "")
    if pending_wp and pending_job == data.get("job_id", "") and draft_html:
        s = await load_settings(ctx)
        if s.get("wp_app_password"):
            try:
                await _post(ctx, "/api/wordpress/update", {
                    "wp_url": s["wp_url"], "wp_user": s["wp_username"],
                    "wp_password": s["wp_app_password"],
                    "post_id": int(pending_wp), "content": draft_html,
                })
                await save_ui_state(ctx, {"pending_wp_edit": "", "pending_wp_edit_job": ""})
                wp_saved = True
            except Exception:
                pass

    await save_ui_state(ctx, {"editor_mode": "preview"})
    return updates, wp_saved


@chat.function(
    "ai_write",
    description=(
        "Generate full AI-written article content with SEO optimization. "
        "ALWAYS USE for: напиши статью, сгенерируй статью, напиши содержимое, "
        "write article with AI, generate article content, AI article, "
        "напиши текст статьи, заполни статью AI, write full article. "
        "Phase 1: keyword enrichment (secondary KWs, LSI, FAQ). "
        "Phase 2: AI writes full article via MOS. Background — result auto-delivered (~60-90s). "
        "DO NOT use for creating empty content placeholders — use new_content for that."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
    background=True,
    long_running=False,
)
async def ai_write(ctx, params: AiWriteParams) -> ActionResult:
    """Background AI article generation — polls MOS job and delivers result to chat."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            return ActionResult.error(error="Content item not found")

        kw           = item.get("keyword", "")
        content_type = item.get("type", "blog")
        existing     = item.get("content", "")
        brief        = item.get("brief", "")
        title        = item.get("title", kw)
        s            = await load_settings(ctx)
        language     = s.get("language", "en")

        # ── Newsletter path ───────────────────────────────────────────────────
        if content_type == "newsletter":
            await ctx.progress(20, "Writing newsletter draft...")
            news_text = existing or item.get("subject", kw) or kw
            data = await _mos_newsletter(ctx, news_text=news_text)
            if "error" in data:
                await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), False, data["error"])
                return ActionResult.error(error=data["error"])
            draft_html   = data.get("content", "")
            subject_line = data.get("subject", "")
            updates: dict = {"content": draft_html, "status": "review"}
            if subject_line and not item.get("subject"): updates["subject"] = subject_line
            if subject_line and not item.get("title"):   updates["title"]   = subject_line
            await update_content(ctx, cid, updates)
            await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), True)
            return ActionResult.success(
                data={"length": len(draft_html)},
                summary=f"Newsletter draft written for '{kw}'",
                refresh_panels=["sidebar", "editor"],
            )

        # ── Improve path ──────────────────────────────────────────────────────
        if params.section == "improve":
            if not existing:
                return ActionResult.error(error="No content to improve. Run AI Write first.")
            await ctx.progress(20, "Improving article with AI...")
            data = await _post(ctx, "/api/content/refine", {
                "user_key":    "",
                "content":     existing,
                "instruction": (
                    f"Improve this article about '{kw}' for SEO and AI-search visibility. "
                    "Add a FAQ section if missing. Improve readability. Make answers more direct."
                ),
            }, timeout=120)
            if "error" in data:
                await log_action(ctx, "ai_write_improve", cid, int((time.monotonic() - t0) * 1000), False, data["error"])
                return ActionResult.error(error=data["error"])
            draft_html = data.get("content", existing)
            await update_content(ctx, cid, {"content": draft_html})
            await log_action(ctx, "ai_write_improve", cid, int((time.monotonic() - t0) * 1000), True)
            return ActionResult.success(
                data={"length": len(draft_html)},
                summary=f"Article improved for '{kw}'",
                refresh_panels=["sidebar", "editor"],
            )

        # ── Full article path — job-based ─────────────────────────────────────
        await ctx.progress(5, "Enriching keywords...")
        kw_data, brand_context = await asyncio.gather(
            keywords_for_article(ctx, kw),
            build_docs_context(ctx),
        )
        secondary  = kw_data.get("secondary_keywords", []) if "error" not in kw_data else []
        lsi        = kw_data.get("lsi_terms", [])           if "error" not in kw_data else []
        questions  = kw_data.get("questions", [])            if "error" not in kw_data else []
        word_count = kw_data.get("word_count", 1400)         if "error" not in kw_data else 1400
        title_opts = kw_data.get("title_options", [])        if "error" not in kw_data else []

        best_title = title_opts[0] if title_opts and not item.get("title") else title

        ser_context = ""
        if item.get("volume") or item.get("difficulty"):
            ser_context = (
                f"Keyword: {kw} | Volume: {item.get('volume', 0)}/mo | Difficulty: {item.get('difficulty', 0)}/100"
            )

        article_type = params.article_type or item.get("type", "blog")
        if brief:
            ser_context = f"CONTENT BRIEF (follow this outline):\n{brief}\n\n{ser_context}".strip()

        await ctx.progress(15, "Starting article generation...")
        job = await start_generate_article(
            ctx,
            topic=best_title or kw,
            keyword=kw,
            article_type=article_type,
            word_count=word_count,
            language=language,
            secondary_keywords=secondary,
            lsi_terms=lsi,
            questions=questions,
            brand_context=brand_context,
            ser_context=ser_context,
        )

        if "error" in job:
            await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), False, job["error"])
            return ActionResult.error(error=job["error"])

        job_id = job.get("job_id", "")
        await update_content(ctx, cid, {
            "generating":         True,
            "job_id":             job_id,
            "secondary_keywords": secondary,
            "title":              best_title or kw,
        })

        # ── Poll until done (max ~150s) ───────────────────────────────────────
        await ctx.progress(20, "AI is writing the article...")
        data = {}
        for i in range(100):
            await asyncio.sleep(1.5)
            data = await poll_article_job(ctx, job_id)
            status = data.get("status", "pending")
            if status != "pending":
                break
            pct = min(88, 20 + int(i * 0.7))
            elapsed = int(time.monotonic() - t0)
            await ctx.progress(pct, f"Generating... ({elapsed}s elapsed)")

        status = data.get("status", "not_found")
        if status in ("not_found", "error"):
            await update_content(ctx, cid, {"generating": False, "job_id": None})
            err = data.get("error", "Generation failed — please try again.")
            await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), False, err)
            return ActionResult.error(error=err)

        await ctx.progress(92, "Saving article...")
        # Stash job_id in data for WP-edit detection in _save_job_result
        data["job_id"] = job_id
        updates, wp_saved = await _save_job_result(ctx, cid, item, data)

        result    = data.get("result", {})
        kw_used   = result.get("word_count", 0)
        final_ttl = result.get("title", "")

        await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"length": len(result.get("content", "")), "word_count": kw_used},
            summary=(
                f"Article ready for '{kw}' (~{kw_used} words).\n"
                f"Title: {final_ttl}\n"
                + (f"✅ Saved to WP post #{updates.get('wp_post_id', '')}.\n" if wp_saved else "")
                + f"Secondary KWs: {', '.join(secondary[:3])}{'...' if len(secondary) > 3 else ''}"
            ),
            refresh_panels=["sidebar", "editor"],
        )

    except Exception as e:
        await log_action(ctx, "ai_write", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "check_article_job",
    description=(
        "Fallback: retrieve a completed article generation job started in a previous session. "
        "Only needed if ai_write was interrupted or started before background support. "
        "Returns 'pending' if still generating."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def check_article_job(ctx, params: AiBriefParams) -> ActionResult:
    """Fallback poll for a completed article job (previous session / interrupted run)."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            return ActionResult.error(error="Content item not found")

        job_id = item.get("job_id", "")
        if not job_id:
            ui_st  = await load_ui_state(ctx)
            job_id = ui_st.get("pending_wp_edit_job", "")
        if not job_id:
            return ActionResult.error(error="No active generation job.")

        data   = await poll_article_job(ctx, job_id)
        status = data.get("status", "not_found")

        if status == "pending":
            return ActionResult.success(
                data={"status": "pending", "job_id": job_id},
                summary="Article is still generating. Check again in ~30 seconds.",
            )

        if status in ("not_found", "error"):
            await update_content(ctx, cid, {"generating": False, "job_id": None})
            err = data.get("error", "Generation failed — please try again.")
            return ActionResult.error(error=err)

        data["job_id"] = job_id
        _, wp_saved = await _save_job_result(ctx, cid, item, data)

        result    = data.get("result", {})
        kw_used   = result.get("word_count", 0)
        final_ttl = result.get("title", "")
        secondary = item.get("secondary_keywords", [])
        kw        = item.get("keyword", "")

        await log_action(ctx, "check_article_job", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"length": len(result.get("content", "")), "word_count": kw_used, "saved_to_wp": wp_saved},
            summary=(
                f"Article ready for '{kw}' (~{kw_used} words).\n"
                f"Title: {final_ttl}\n"
                + (f"✅ Saved to WP.\n" if wp_saved else "")
                + f"Secondary KWs: {', '.join(secondary[:3])}{'...' if len(secondary) > 3 else ''}"
            ),
            refresh_panels=["sidebar", "editor"],
        )
    except Exception as e:
        await log_action(ctx, "check_article_job", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))
