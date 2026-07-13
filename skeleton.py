"""Skeleton context providers for Article Writer.

Per Imperal SDK: skeleton = LLM context cache holding ready API responses.
More data here = better Webbee routing and answers, with zero extra
round-trips. Never carries full article bodies — same rule as the chat
functions (response_models.ArticleSummary docstring).
"""
from app import ext
from api_client import call_backend


@ext.skeleton("article_writer_overview", ttl=60,
              description="Article Writer projects + article counts by status — degrades to zeros if backend unreachable")
async def skeleton_refresh_overview(ctx) -> dict:
    projects_data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    projects = projects_data.get("data") if isinstance(projects_data.get("data"), list) else []
    projects = projects or []

    articles_data = await call_backend(ctx, "GET", "/v1/articles", params={"limit": 200, "offset": 0})
    articles = articles_data.get("data") if isinstance(articles_data.get("data"), list) else []
    articles = articles or []

    by_status = {"idea": 0, "writing": 0, "review": 0, "published": 0}
    for a in articles:
        s = a.get("status", "idea")
        by_status[s] = by_status.get(s, 0) + 1

    if not projects and "error" in projects_data:
        instruction = (
            "Article Writer backend is unreachable right now — tell the user generation/project "
            "actions may fail, but don't block on it."
        )
    elif not projects:
        instruction = "No projects yet — create one with create_project before writing articles."
    else:
        instruction = (
            f"{len(projects)} project(s), {len(articles)} article(s) total: "
            + ", ".join(f"{v} {k}" for k, v in by_status.items())
            + ". Use list_projects/list_articles for details, generate_article to write, "
              "patch_article to edit a specific part."
        )

    return {"response": {
        "project_count": len(projects),
        "article_count": len(articles),
        "by_status": by_status,
        "instruction": instruction,
    }}
