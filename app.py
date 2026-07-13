"""Article Writer extension — core init + shared helpers.

Architecture (mirrors se-ranking-connector's / matomo-analytics-extension's
shared-backend pattern — see article-writer-backend/PLAN.md for the full
target design):

  - Webbee assembles a project's context (keywords, brand voice, useful
    links, socials, source facts) using web search and whatever other
    extensions are installed (SE Ranking, GSC, Matomo, etc.) — THIS
    extension has no idea those exist. It only persists that context and
    hands it to the backend when asked to generate or patch an article.

  - The extension calls a SHARED backend microservice (article-writer-api)
    that owns the Galera-backed database and the whole generation pipeline
    (outline -> draft -> mechanical gates -> grounding -> judge -> revise).
    The backend is multi-tenant by platform identity: every request carries
    the caller's `imperal_id` as `X-Imperal-Id`, and the backend scopes
    every query to it — never an external per-user API key, since there is
    no external account here (unlike SE Ranking).

  - article-writer-api requires a platform JWT on every call. That token is
    NOT a per-user credential — it identifies this extension to the
    backend, same value for every installer — so it's declared as an
    ext.secret with write_mode="extension" (developer-set only, via
    developer.save_app_secret; never entered by end users, never
    committed to source).

  - Full article bodies are read/edited ONLY through this extension's
    panel, which calls the backend directly with plain Python (zero LLM
    tokens, any corpus size). Chat-facing functions never return a full
    article body — only metadata (see response_models.ArticleSummary).
"""
from __future__ import annotations

import os

from imperal_sdk import Extension, ChatExtension

# Shared backend bridge — same public API gateway host every extension on
# this platform calls. Not a secret: it's the platform's own microservice.
SERVER_URL = os.environ.get("ARTICLE_WRITER_BACKEND_URL", "") or "https://api.webhostmost.com/article-writer"

ext = Extension(
    "imperal-article-writer-extension",
    version="2.0.0",
    display_name="Article Writer",
    description=(
        "Project-based SEO article writing: keep per-site context (keywords, brand voice, "
        "useful links, socials) and have articles written cheaply, with self-review, grounded "
        "in that context. Read/edit full articles in the panel — chat never touches full bodies."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[
        "Project Context Store",
        "AI Article Generation",
        "Grounded Self-Review",
        "Panel Article Editor",
        "Natural-Language Article Patching",
    ],
)

chat = ChatExtension(
    ext,
    tool_name="article_writer",
    description=(
        "Article Writer — project-based SEO article writing. Use for: create/update a project's "
        "context (keywords, brand voice, links, socials — создай проект, обнови контекст проекта), "
        "list projects/articles (покажи проекты, покажи статьи), create an article and generate "
        "its draft (напиши статью, сгенерируй статью), check generation status, patch a specific "
        "part of an article by instruction (перепиши абзац про доставку), change article status "
        "(idea/writing/review/published). Never returns full article bodies to chat — full text "
        "is read/edited only in the Article Writer panel."
    ),
    max_rounds=10,
)

ext.secret(
    name="backend_jwt",
    description=(
        "Platform JWT authenticating this extension to the article-writer-api backend "
        "microservice. Developer-managed only — never entered or seen by end users."
    ),
    required=True,
    scope="app",  # app-scope secrets are owner-only regardless of write_mode
    env_fallback="IMPERAL_APPSECRET_ARTICLE_WRITER_BACKEND_JWT",
    max_bytes=2048,
)(lambda: None)


@ext.health_check
async def health(ctx) -> dict:
    """Report whether the backend JWT is configured."""
    jwt = await ctx.secrets.get("backend_jwt")
    return {"status": "ok" if jwt else "degraded", "version": ext.version}
