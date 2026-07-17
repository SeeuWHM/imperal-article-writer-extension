"""Skeleton context providers for Article Writer.

Per Imperal SDK: skeleton = LLM context cache holding ready API responses.
More data here = better Webbee routing and answers, with zero extra
round-trips. Never carries full article bodies — same rule as the chat
functions (response_models.ArticleSummary docstring).
"""
from app import ext
from api_client import call_backend


@ext.skeleton("article_writer_overview", ttl=60, alert=True,
              description="Article Writer projects + article counts by status — degrades to zeros if backend unreachable")
async def skeleton_refresh_overview(ctx) -> dict:
    projects_data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    projects = projects_data.get("data") if isinstance(projects_data.get("data"), list) else []
    projects = projects or []

    # limit must be <= 100 (backend caps it via Query(le=100)); 200 returned a
    # 422 every refresh, so article counts never populated. Use the paged
    # `total` for the true count regardless of page size.
    articles_data = await call_backend(ctx, "GET", "/v1/articles", params={"limit": 100, "offset": 0})
    articles = articles_data.get("data") if isinstance(articles_data.get("data"), list) else []
    articles = articles or []

    project_count = projects_data.get("total", len(projects)) if isinstance(projects_data, dict) else len(projects)
    article_count = articles_data.get("total", len(articles)) if isinstance(articles_data, dict) else len(articles)

    by_status = {"idea": 0, "writing": 0, "review": 0, "published": 0}
    for a in articles:
        s = a.get("status", "idea")
        by_status[s] = by_status.get(s, 0) + 1

    # Title of the most-recently-updated article sitting in "review" — this is
    # what a just-finished generation lands as. The paired alert tool fires
    # when the review count goes up and names this one, so Webbee can
    # proactively tell the user "<title> is ready" the moment it's written.
    review_items = [a for a in articles if a.get("status") == "review"]
    latest_ready = ""
    if review_items:
        newest = max(review_items, key=lambda a: a.get("updated_at") or "")
        latest_ready = (newest.get("title") or newest.get("target_keyword") or "(untitled)")[:60]

    if not projects and "error" in projects_data:
        instruction = (
            "Article Writer backend is unreachable right now — tell the user generation/project "
            "actions may fail, but don't block on it."
        )
    elif not projects:
        instruction = "No projects yet — create one with create_project before writing articles."
    else:
        instruction = (
            f"{project_count} project(s), {article_count} article(s) total: "
            + ", ".join(f"{v} {k}" for k, v in by_status.items())
            + ". Use list_projects/list_articles for details, generate_article to write, "
              "patch_article to edit a specific part."
        )

    return {"response": {
        "project_count": project_count,
        "article_count": article_count,
        "by_status": by_status,
        "latest_ready": latest_ready,
        "instruction": instruction,
    }}


@ext.tool(
    "skeleton_alert_article_writer_overview",
    description="Fires when an article finishes generating and lands in 'review' — proactive 'your article is ready' notice.",
)
async def skeleton_alert_article_writer_overview(ctx, old: dict | None = None, new: dict | None = None) -> dict:
    """Compare the previous vs current skeleton snapshot; if the number of
    articles in 'review' went up, a generation just finished — return a short
    notice naming the newest one so Webbee tells the user proactively.
    Returns {"response": ""} (no alert) on first snapshot or no change."""
    try:
        if not old or not new:
            return {"response": ""}
        old_review = int((old.get("by_status") or {}).get("review", 0))
        new_review = int((new.get("by_status") or {}).get("review", 0))
        if new_review <= old_review:
            return {"response": ""}
        latest = (new.get("latest_ready") or "").strip()
        added = new_review - old_review
        if latest and added == 1:
            return {"response": f'Your article "{latest}" is written and ready for review in the Article Writer panel.'}
        return {"response": f"{added} articles just finished and are ready for review in the Article Writer panel."}
    except Exception:
        return {"response": ""}
