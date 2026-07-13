"""Chat-function handlers: AI generation and natural-language patching.

These are the ONLY two ways an article's content should actually get
written — both run through the backend's real pipeline (outline -> draft ->
mechanical gates -> grounding -> judge -> targeted revision for generate;
locate -> edit -> rescore for patch). Neither ever returns a full body —
generate_article returns a job you poll; patch_article returns a short
preview (see response_models.PatchResult).
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend, GENERATE_TIMEOUT, PATCH_TIMEOUT
from params import GenerateArticleParams, GenerationJobStatusParams, PatchArticleParams
from response_models import GenerationJobResponse, GenerationStatusResponse, PatchResult


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


@chat.function(
    "generate_article",
    description=(
        "Start writing an article's first draft using the project's context plus a brief and "
        "any real source facts (from web search or other extensions) it must be grounded in. "
        "Runs in the background — call check_generation_status with the returned job_id to see "
        "when it's done (status lands on 'review'). Use for: напиши статью, сгенерируй статью, "
        "write the article, draft this article."
    ),
    action_type="write",
    event="article-writer.article.generation_started",
    effects=["update:article"],
    data_model=GenerationJobResponse,
)
async def fn_generate_article(ctx, params: GenerateArticleParams) -> ActionResult:
    """Enqueue the full generation pipeline for an article; returns a job to poll."""
    body = params.model_dump(exclude_none=True, exclude={"article_id"})
    data = await call_backend(
        ctx, "POST", f"/v1/articles/{params.article_id}/generate", json=body, timeout=GENERATE_TIMEOUT,
    )
    if "error" in data:
        return _err(data)
    result = GenerationJobResponse(
        job_id=data.get("id") or data.get("job_id", ""), article_id=params.article_id,
        status=data.get("status", "queued"),
    )
    return ActionResult.success(
        data=result, summary=f"Generation started (job {result.job_id}).", refresh_panels=["workspace"],
    )


@chat.function(
    "check_generation_status",
    description=(
        "Check progress of a generate_article job — status, model used, cost. Use for: готова "
        "ли статья, is the article done, check generation status."
    ),
    action_type="read",
    chain_callable=True,
    data_model=GenerationStatusResponse,
)
async def fn_check_generation_status(ctx, params: GenerationJobStatusParams) -> ActionResult:
    """Poll a generate_article job's status/cost."""
    data = await call_backend(ctx, "GET", f"/v1/articles/{params.article_id}/jobs/{params.job_id}")
    if "error" in data:
        return _err(data)
    result = GenerationStatusResponse(
        job_id=data.get("id", params.job_id), status=data.get("status", "unknown"),
        model=data.get("model"), tokens_used=data.get("tokens_used"),
        cost_estimate=data.get("cost_estimate"), error=data.get("error"),
    )
    return ActionResult.success(data=result, summary=f"Job status: {result.status}.")


@chat.function(
    "patch_article",
    description=(
        "Rewrite ONE part of an article by natural-language instruction (e.g. 'rewrite the "
        "paragraph about delivery', 'make the intro punchier'). Locates the right section "
        "automatically, edits just that section, and recomputes word count/SEO flags — never "
        "touches the rest of the article. Returns a short preview, not the full body. Use for: "
        "перепиши абзац про X, rewrite the section about X, fix the intro, tighten the "
        "conclusion."
    ),
    action_type="write",
    event="article-writer.article.patched",
    effects=["update:article"],
    data_model=PatchResult,
)
async def fn_patch_article(ctx, params: PatchArticleParams) -> ActionResult:
    """Locate and rewrite one section by natural-language instruction."""
    body = params.model_dump(exclude_none=True, exclude={"article_id"})
    data = await call_backend(
        ctx, "POST", f"/v1/articles/{params.article_id}/patch", json=body, timeout=PATCH_TIMEOUT,
    )
    if "error" in data:
        return _err(data)
    seo_score = data.get("seo_score") or {}
    result = PatchResult(
        section_id=data.get("section_id", ""), order_index=data.get("order_index", 0),
        heading=data.get("heading"), preview=data.get("preview", ""),
        word_count=seo_score.get("word_count", 0), seo_flags=seo_score.get("flags") or [],
    )
    return ActionResult.success(
        data=result, summary=f'Updated section "{result.heading or result.order_index}".',
        refresh_panels=["workspace"],
    )
