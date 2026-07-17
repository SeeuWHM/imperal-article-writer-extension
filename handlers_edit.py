"""Chat-function handlers: Webbee's full-text read + edit of an article.

Deliberately relaxes the "never return body to chat" rule for two explicit
tools the site owner asked for: Webbee can read the whole article as Markdown
and replace it wholesale with an edited version. The save is deterministic
(markdown_to_document -> verbatim sections), so what Webbee submits is exactly
what gets stored — no re-generation. For small targeted edits, patch_article
(handlers_generate.py) stays the lighter option.

Split out of handlers_articles.py to keep that file under the 300-line guideline.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend
from richtext import document_to_markdown, markdown_to_document
from params import ArticleIdParams, EditFullArticleParams
from response_models import ArticleTextRecord, ArticleSummary
from handlers_articles import _err, _to_summary


@chat.function(
    "read_full_article",
    description=(
        "Read the ENTIRE article body as editable Markdown (# title, ## section headings, body in "
        "light markdown). Returns the full text to chat on purpose — call this before editing so "
        "you work from the real current text, never from memory. (To hand an article to another "
        "app like Mail/Notes, use export_article_text instead.) Use for: "
        "read the whole article."
    ),
    action_type="read",
    data_model=ArticleTextRecord,
)
async def fn_read_full_article(ctx, params: ArticleIdParams) -> ActionResult:
    """Return the whole article as Markdown for Webbee to read/edit."""
    data = await call_backend(ctx, "GET", f"/v1/articles/{params.article_id}")
    if "error" in data:
        return _err(data)
    md = document_to_markdown(data.get("title") or "", data.get("sections") or [])
    result = ArticleTextRecord(
        id=data.get("id", params.article_id), title=data.get("title"),
        status=data.get("status", "idea"), word_count=data.get("word_count", 0), markdown=md,
    )
    return ActionResult.success(data=result, summary=f"Full article text ({result.word_count} words).")


@chat.function(
    "edit_full_article",
    description=(
        "Replace the ENTIRE article with your edited version as Markdown (# title, ## headings, "
        "body). Stores EXACTLY what you submit — nothing is re-generated — so first "
        "read_full_article, change only what's needed, and resend the COMPLETE text with every "
        "unchanged part preserved verbatim. For a small targeted change prefer patch_article. "
        "Use for: edit the article."
    ),
    action_type="write",
    event="article-writer.article.section_saved",
    effects=["update:article"],
    data_model=ArticleSummary,
)
async def fn_edit_full_article(ctx, params: EditFullArticleParams) -> ActionResult:
    """Webbee's full-text edit — split submitted Markdown into title + sections, store verbatim."""
    title, sections = markdown_to_document(params.content_markdown)
    if not sections:
        return ActionResult.error(
            error="Nothing to save — the submitted text is empty.", code="VALIDATION_MISSING_FIELD",
        )
    data = await call_backend(
        ctx, "PUT", f"/v1/articles/{params.article_id}/sections", json={"sections": sections},
    )
    if "error" in data:
        return _err(data)
    latest = data
    if title:
        meta = await call_backend(
            ctx, "PATCH", f"/v1/articles/{params.article_id}/meta", json={"title": title},
        )
        if isinstance(meta, dict) and "error" in meta:
            return _err(meta)
        latest = meta
    result = _to_summary(latest) if isinstance(latest, dict) and latest.get("id") else ArticleSummary(id=params.article_id)
    return ActionResult.success(data=result, summary="Article updated.", refresh_panels=["workspace"])
