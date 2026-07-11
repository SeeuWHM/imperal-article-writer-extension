"""AI improvement and newsletter handlers."""
import asyncio
import time

from imperal_sdk import ActionResult

from wpb_app import chat, get_content, update_content, save_ui_state
from api_client import start_refine_article, poll_article_job, generate_newsletter_mos as _mos_newsletter, log_action
from handlers_content import _resolve_id
from params import ImproveArticleParams, GenerateNewsletterParams


@chat.function(
    "improve_article",
    description=(
        "Fully improve/rewrite the current article for SEO and quality. "
        "Use when user says: improve article, make it better, full rewrite, "
        "улучши статью, перепиши полностью, сделай лучше, SEO улучшение, "
        "добавь FAQ, оптимизируй под SEO. "
        "Adds FAQ, sharpens structure, improves keyword density. Async — ~60s."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
    background=True,
    long_running=False,
)
async def improve_article(ctx, params: ImproveArticleParams) -> ActionResult:
    """Start async article improvement via MOS refine endpoint."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            return ActionResult.error(error="Content item not found")

        existing = item.get("content", "")
        if not existing:
            return ActionResult.error(error="No content to improve. Run AI Write first.")

        kw = item.get("keyword", "")
        instruction = params.instruction or (
            f"Improve this article about '{kw}' for SEO and Rank Math optimization. "
            f"CRITICAL: The focus keyword '{kw}' MUST appear in the FIRST sentence AND in at least 2 H2 headings. "
            f"Target keyword density: 0.5-1% (use '{kw}' ~12-15 times in 2500 words). "
            "Add FAQ section if missing (5-7 questions, each answerable by AI assistants). "
            "Add comparison table with hosting providers/plans if not present. "
            "Sharpen H2 structure — each H2 must answer one specific question and contain the keyword or a variant. "
            "Make answers more direct and quotable. "
            "Ensure every factual claim includes a specific number or example. "
            "Add 2-3 outbound DoFollow links to authoritative sources. "
            "Do NOT remove or change existing outbound/internal links. "
            "Maintain article length ≥2500 words."
        )

        job = await start_refine_article(ctx, content=existing, keyword=kw, instruction=instruction)

        if "error" in job:
            await log_action(ctx, "improve_article", cid, int((time.monotonic() - t0) * 1000), False, job["error"])
            return ActionResult.error(error=job["error"])

        job_id = job.get("job_id", "")
        await update_content(ctx, cid, {"generating": True, "job_id": job_id})

        await ctx.progress(20, "Improving article with AI...")
        data = {}
        for i in range(80):
            await asyncio.sleep(1.5)
            data = await poll_article_job(ctx, job_id)
            if data.get("status", "pending") != "pending":
                break
            await ctx.progress(min(88, 20 + i), f"Improving... ({int(time.monotonic()-t0)}s)")

        if data.get("status") in ("not_found", "error"):
            await update_content(ctx, cid, {"generating": False, "job_id": None})
            err = data.get("error", "Improvement failed.")
            await log_action(ctx, "improve_article", cid, int((time.monotonic() - t0) * 1000), False, err)
            return ActionResult.error(error=err)

        result     = data.get("result", {})
        draft_html = result.get("content", "")
        await update_content(ctx, cid, {"content": draft_html, "generating": False, "job_id": None})
        await log_action(ctx, "improve_article", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"length": len(draft_html), "word_count": result.get("word_count", 0)},
            summary=f"Article improved for '{kw}' (~{result.get('word_count', 0)} words).",
            refresh_panels=["sidebar"],
        )
    except Exception as e:
        await log_action(ctx, "improve_article", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "generate_newsletter",
    description="Write a newsletter from a news item or topic. Uses brand voice from Settings.",
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def generate_newsletter(ctx, params: GenerateNewsletterParams) -> ActionResult:
    """Write a newsletter from a topic or news text."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id)
    try:
        item = await get_content(ctx, cid)
        if not item:
            await log_action(ctx, "generate_newsletter", cid, int((time.monotonic() - t0) * 1000), False, "Content item not found")
            return ActionResult.error(error="Content item not found")

        data = await _mos_newsletter(ctx, news_text=params.news_text, tone_note=params.tone_note or "")
        if "error" in data:
            await log_action(ctx, "generate_newsletter", cid, int((time.monotonic() - t0) * 1000), False, data["error"])
            return ActionResult.error(error=data["error"])

        newsletter_html = data.get("content", "")
        subject_line    = data.get("subject", "")

        updates: dict = {"content": newsletter_html, "status": "review"}
        if subject_line and not item.get("subject"): updates["subject"] = subject_line
        if subject_line and not item.get("title"):   updates["title"]   = subject_line

        await update_content(ctx, cid, updates)
        await save_ui_state(ctx, {"editor_mode": "preview"})
        await log_action(ctx, "generate_newsletter", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"subject": subject_line, "length": len(newsletter_html)},
            summary=f"Newsletter written. Subject: {subject_line}",
        )
    except Exception as e:
        await log_action(ctx, "generate_newsletter", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))
