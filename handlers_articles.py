"""Chat-function handlers: articles — metadata CRUD only.

Full article bodies are read/edited exclusively in the panel
(panels_workspace.py), which calls the backend directly with plain Python —
zero LLM tokens regardless of corpus size. None of the functions here ever
return a full body — see response_models.ArticleSummary's docstring.

save_article_section and save_full_article are the two exceptions that touch
content — both are raw manual-overwrite paths, no AI involved (content is
whatever the human typed, not something an LLM produced), and both
deliberately bypass the whole outline/draft/grounding/judge pipeline:
  - save_article_section: one section by exact order_index — usable from
    chat when a user pastes/dictates verbatim text.
  - save_full_article: PANEL-ONLY — the single merged-editor's Save button.
    Splits the whole document back into sections at heading boundaries
    (richtext.html_to_sections), so it's the one place a user can add/
    remove/reorder sections just by editing headings.
Their descriptions steer Webbee toward generate_article / patch_article
(handlers_generate.py) for anything that should actually be *written*.

export_article_text is the one function that DOES return a full body — see
response_models.ArticleFullText's docstring for why that's a deliberate,
narrow exception rather than a hole in the token-economy guarantee.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend, _err
from richtext import from_html, html_to_document, sections_to_html, to_export_text
from params import (
    CreateArticleParams, ListArticlesParams, ArticleIdParams,
    UpdateArticleStatusParams, UpdateArticleMetaParams, SaveArticleSectionParams,
    SaveFullArticleParams,
)
from response_models import ArticleSummary, ArticleListResponse, DeletedResponse, ArticleFullText


def _to_summary(a: dict) -> ArticleSummary:
    seo_score = a.get("seo_score") or {}
    return ArticleSummary(
        id=a.get("id", ""), project_id=a.get("project_id", ""), title=a.get("title"),
        status=a.get("status", "idea"), target_keyword=a.get("target_keyword"),
        meta_description=a.get("meta_description"),
        word_count=a.get("word_count", 0), seo_flags=seo_score.get("flags") or [],
        model_used=a.get("model_used"),
    )


@chat.function(
    "create_article",
    description=(
        "Create a new article shell under a project — just a title/keyword placeholder, no "
        "content yet. Use for: add an article idea. Follow up "
        "with generate_article to actually write it."
    ),
    action_type="write",
    event="article-writer.article.created",
    effects=["create:article"],
    data_model=ArticleSummary,
)
async def fn_create_article(ctx, params: CreateArticleParams) -> ActionResult:
    """Create an empty article shell under a project — no AI call yet."""
    data = await call_backend(ctx, "POST", "/v1/articles", json=params.model_dump(exclude_none=True))
    if "error" in data:
        return _err(data)
    summary = _to_summary(data)
    return ActionResult.success(
        data=summary, summary=f'Created article "{summary.title or summary.target_keyword or summary.id}".',
        refresh_panels=["workspace"],
    )


@chat.function(
    "list_articles",
    description=(
        "List articles (metadata only — id, title, status, word count, SEO flags — never the "
        "full text). Optionally filter by project or status. Use for: list "
        "articles, what's in review, show idea/writing/review/published articles."
    ),
    action_type="read",
    chain_callable=True,
    data_model=ArticleListResponse,
)
async def fn_list_articles(ctx, params: ListArticlesParams) -> ActionResult:
    """Return article metadata only, optionally filtered by project/status."""
    q = {"limit": 100, "offset": 0}
    if params.project_id:
        q["project_id"] = params.project_id
    if params.status:
        q["status"] = params.status
    data = await call_backend(ctx, "GET", "/v1/articles", params=q)
    if "error" in data:
        return _err(data)
    raw = data.get("data") if isinstance(data.get("data"), list) else data.get("items") or []
    articles = [_to_summary(a) for a in raw]
    result = ArticleListResponse(articles=articles, count=len(articles))
    rows = [
        {"title": a.title or "(untitled)", "status": a.status, "word_count": a.word_count,
         "flags": ", ".join(a.seo_flags) or "-"}
        for a in articles
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="title", label="Article", width="35%"),
            ui.DataColumn(key="status", label="Status", width="15%"),
            ui.DataColumn(key="word_count", label="Words", width="15%"),
            ui.DataColumn(key="flags", label="Flags", width="35%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No articles yet.")
    return ActionResult.success(data=result, summary=f"{len(articles)} article(s)", ui=ui_node)


@chat.function(
    "update_article_status",
    description=(
        "Move an article to a new status: idea, writing, review, or published. Use for: "
        "mark as review, move to writing."
    ),
    action_type="write",
    event="article-writer.article.status_changed",
    effects=["update:article"],
    data_model=ArticleSummary,
)
async def fn_update_article_status(ctx, params: UpdateArticleStatusParams) -> ActionResult:
    """Move an article to a new pipeline status."""
    data = await call_backend(ctx, "PATCH", f"/v1/articles/{params.article_id}/status", json={"status": params.status})
    if "error" in data:
        return _err(data)
    summary = _to_summary(data)
    return ActionResult.success(
        data=summary, summary=f"Status set to {summary.status}.", refresh_panels=["workspace"],
    )


@chat.function(
    "update_article_meta",
    description=(
        "Fix an article's SEO metadata — title, meta_description, and/or target_keyword — "
        "WITHOUT touching the article body/sections. This is the only way to clear a "
        "meta_description SEO flag (e.g. 'length outside 70-165') or correct the target "
        "keyword after generation. Use for: fix the meta description, "
        "update SEO title/keyword. To rewrite actual body text, use patch_article instead."
    ),
    action_type="write",
    event="article-writer.article.meta_updated",
    effects=["update:article"],
    data_model=ArticleSummary,
)
async def fn_update_article_meta(ctx, params: UpdateArticleMetaParams) -> ActionResult:
    """Partial fix for title/meta_description/target_keyword — recomputes SEO flags."""
    fields = params.model_dump(exclude_none=True, exclude={"article_id"})
    if not fields:
        return ActionResult.error(
            error="Nothing to update — provide title, meta_description, and/or target_keyword.",
            code="VALIDATION_MISSING_FIELD",
        )
    data = await call_backend(ctx, "PATCH", f"/v1/articles/{params.article_id}/meta", json=fields)
    if "error" in data:
        return _err(data)
    summary = _to_summary(data)
    return ActionResult.success(
        data=summary, summary="SEO metadata updated.", refresh_panels=["workspace"],
    )


@chat.function(
    "save_article_section",
    description=(
        "Directly overwrite one section's heading/content with EXACT text you were given — a "
        "raw manual save, NOT an AI writing step (it skips grounding/review entirely). Use only "
        "when the user pastes/dictates exact text to store verbatim. To actually WRITE or "
        "improve an article, use generate_article or patch_article instead."
    ),
    action_type="write",
    event="article-writer.article.section_saved",
    effects=["update:article"],
    data_model=DeletedResponse,
)
async def fn_save_article_section(ctx, params: SaveArticleSectionParams) -> ActionResult:
    """Overwrite one section's heading/content verbatim — no AI involved.

    content may arrive as HTML from the panel's RichEditor; from_html() is a
    no-op on plain text, so this is safe regardless of caller (panel or chat).
    """
    fields = params.model_dump(exclude_none=True, exclude={"article_id", "order_index"})
    if "content" in fields:
        fields["content"] = from_html(fields["content"])
    if not fields:
        return ActionResult.error(
            error="Nothing to save — provide heading and/or content.", code="VALIDATION_MISSING_FIELD",
        )
    data = await call_backend(
        ctx, "PATCH", f"/v1/articles/{params.article_id}/sections/{params.order_index}", json=fields,
    )
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(deleted=False), summary="Section saved.", refresh_panels=["workspace"],
    )


@chat.function(
    "save_full_article",
    description=(
        "PANEL-ONLY: replace the entire article from the panel's single merged editor. The "
        "leading <h1> is the title; everything after it splits into sections at heading "
        "boundaries. Persists BOTH the title and the body in one save — this is the one path "
        "that lets the title or a section be edited/added/removed/reordered by editing the "
        "document directly. "
        "Not for chat use — Webbee should use generate_article or patch_article to write content."
    ),
    action_type="write",
    event="article-writer.article.section_saved",
    effects=["update:article"],
    data_model=DeletedResponse,
)
async def fn_save_full_article(ctx, params: SaveFullArticleParams) -> ActionResult:
    """Panel's single-editor Save — split the merged HTML into title (<h1>) +
    body sections, and persist both."""
    title, sections = html_to_document(params.content_html)
    data = await call_backend(
        ctx, "PUT", f"/v1/articles/{params.article_id}/sections",
        json={"sections": sections},
    )
    if "error" in data:
        return _err(data)
    # Persist the title too (never blank it — if the editor has no leading
    # <h1>, keep whatever title the backend already has).
    if title:
        meta = await call_backend(
            ctx, "PATCH", f"/v1/articles/{params.article_id}/meta", json={"title": title},
        )
        if isinstance(meta, dict) and "error" in meta:
            return _err(meta)
    return ActionResult.success(
        data=DeletedResponse(deleted=False), summary="Article saved.", refresh_panels=["workspace"],
    )


@chat.function(
    "delete_article",
    description="Permanently delete an article. Use for: delete this article.",
    action_type="destructive",
    event="article-writer.article.deleted",
    effects=["delete:article"],
    data_model=DeletedResponse,
)
async def fn_delete_article(ctx, params: ArticleIdParams) -> ActionResult:
    """Permanently delete a single article."""
    data = await call_backend(ctx, "DELETE", f"/v1/articles/{params.article_id}")
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(), summary="Article deleted.", refresh_panels=["workspace"],
    )


@chat.function(
    "export_article_text",
    description=(
        "Get the FULL article body — both as HTML (`html`: <h2>/<strong>/<ul> markup) and plain "
        "text (`text`) — so it can be handed to another extension or the user: sending it by "
        "email, saving it to a note, pasting it elsewhere. Use `html` with Mail's send()/reply() "
        "(is_html=true) or Notes' create_note content for real formatting; use `text` for a "
        "plain fallback. ONLY call this when the user explicitly asks to send/export/copy the "
        "article somewhere. Never call this for routine status checks, listing, or quality "
        "review — use list_articles for those, which stays cheap on purpose."
    ),
    action_type="read",
    data_model=ArticleFullText,
)
async def fn_export_article_text(ctx, params: ArticleIdParams) -> ActionResult:
    """The one deliberate exception to 'never return body to chat' — explicit export only."""
    data = await call_backend(ctx, "GET", f"/v1/articles/{params.article_id}")
    if "error" in data:
        return _err(data)
    sections = data.get("sections") or []
    result = ArticleFullText(
        id=data.get("id", params.article_id), title=data.get("title"),
        meta_description=data.get("meta_description"),
        text=to_export_text(sections), html=sections_to_html(sections),
    )
    return ActionResult.success(data=result, summary=f"Exported {data.get('word_count', 0)} word(s).")
