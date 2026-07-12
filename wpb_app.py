"""Article Writer extension — core init, settings, store helpers."""
from __future__ import annotations

from imperal_sdk import Extension, ChatExtension
from params import UIStateModel

ext = Extension(
    "imperal-article-writer-extension",
    version="1.5.3",
    display_name="Article Writer",
    description="AI-powered WordPress content studio: keyword research, SE Rankings tracking, AI article writing with SEO optimization, and one-click publishing to WordPress.",
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[
        "AI Article Writing",
        "WordPress Publishing",
        "SEO Keyword Research",
        "SE Ranking Tracking",
        "Content Plan Builder",
        "Rank Math SEO Setup",
        "Keyword Management",
    ],
)

chat = ChatExtension(
    ext,
    tool_name="article_writer",
    description=(
        "Article Writer — SEO, content and Google Search Console tool. "
        "ALWAYS use for: Google search positions/rankings (покажи позиции в Google, SEO rankings), "
        "keyword research (найди ключевые слова), "
        "content plan (придумай контент план для блога), "
        "write/rewrite articles (напиши статью), "
        "WordPress: publish, draft, show posts, SEO settings, "
        "SE Ranking tracking, "
        "GSC отчёт, Google Search Console, покажи GSC, клики из Google, "
        "аномалии трафика, что падает что растёт, органический трафик Google, "
        "покажи органику, GSC данные, search console отчёт."
    ),
    max_rounds=10,
)


@ext.cache_model("ui_state")
class _UIStateCache(UIStateModel):
    pass

SETTINGS_COL = "seo_settings"
CONTENT_COL = "seo_content"
UI_STATE_COL = "seo_ui_state"

DEFAULT_SETTINGS: dict = {
    "backend_url": "",
    "backend_api_key": "",
    "seranking_api_key": "",
    "seranking_project_id": "",
    "seranking_domain": "",
    "seranking_source": "us",
    "wp_url": "",
    "wp_username": "",
    "wp_app_password": "",
    "wp_author_id": 1,
    # Google Search Console — paste any Google JSON key here (SA or authorized_user)
    "gsc_site_url": "sc-domain:webhostmost.com",
    "gsc_credentials_json": "",
    # Legacy fields kept for backwards compat
    "gsc_service_account": "",
    "gsc_oauth_client_id": "",
    "gsc_oauth_client_secret": "",
    "gsc_oauth_refresh_token": "",
    "company_name": "",
    "brand_description": "",
    "brand_voice": "Direct and smart. Short punchy sentences. Bold without being arrogant. No corporate fluff.",
    "newsletter_cta": "Learn more",
    "site_url": "",
    "blog_url": "",
    "tg_url": "",
    "community_url": "",
}

DEFAULT_UI_STATE: dict = {
    "active_view": "plan",
    "selected_id": None,
    "editor_mode": "edit",
    "kw_results": [],
    "rankings_results": [],
}


# ── Settings ──────────────────────────────────────────────────────────────────

async def load_settings(ctx) -> dict:
    try:
        page = await ctx.store.query(SETTINGS_COL, limit=1)
    except Exception:
        return dict(DEFAULT_SETTINGS)
    docs = getattr(page, "data", None) or []
    if docs and isinstance(getattr(docs[0], "data", None), dict):
        return {**DEFAULT_SETTINGS, **docs[0].data}
    return dict(DEFAULT_SETTINGS)


async def save_settings(ctx, values: dict) -> dict:
    current = await load_settings(ctx)
    merged = {**current, **{k: v for k, v in values.items() if v is not None and v != ""}}
    page = await ctx.store.query(SETTINGS_COL, limit=1)
    docs = getattr(page, "data", None) or []
    if docs:
        await ctx.store.update(SETTINGS_COL, docs[0].id, merged)
    else:
        await ctx.store.create(SETTINGS_COL, merged)
    return merged


# ── UI state ──────────────────────────────────────────────────────────────────

async def load_ui_state(ctx) -> dict:
    try:
        page = await ctx.store.query(UI_STATE_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs and isinstance(getattr(docs[0], "data", None), dict):
            return {**DEFAULT_UI_STATE, **docs[0].data}
    except Exception:
        pass
    return dict(DEFAULT_UI_STATE)


async def save_ui_state(ctx, values: dict, persist: bool = False) -> dict:
    current = await load_ui_state(ctx)
    merged = {**current, **{k: v for k, v in values.items() if v is not None}}
    try:
        page = await ctx.store.query(UI_STATE_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs:
            await ctx.store.update(UI_STATE_COL, docs[0].id, merged)
        else:
            await ctx.store.create(UI_STATE_COL, merged)
    except Exception:
        pass
    return merged


# ── Content store — MOS primary, ctx.store fallback ───────────────────────────

async def _store_list(ctx) -> list[dict]:
    try:
        page = await ctx.store.query(CONTENT_COL, limit=200)
        docs = getattr(page, "data", None) or []
        items = []
        for d in docs:
            if isinstance(getattr(d, "data", None), dict):
                item = dict(d.data)
                item["id"] = d.id
                items.append(item)
        return items
    except Exception:
        return []


async def list_content(ctx, status: str | None = None) -> list[dict]:
    # Always merge MOS + ctx.store so old ideas don't disappear when MOS has newer items
    mos_items: list = []
    try:
        from api_client import mos_content_list
        mos_items = await mos_content_list(ctx) or []
    except Exception:
        mos_items = []

    store_items = await _store_list(ctx)

    # Deduplicate: MOS wins on ID collision
    seen_ids = {i.get("id") for i in mos_items if i.get("id")}
    merged = mos_items + [i for i in store_items if i.get("id") not in seen_ids]

    if status:
        merged = [i for i in merged if i.get("status") == status]
    return merged


async def get_content(ctx, content_id: str) -> dict | None:
    if not content_id:
        return None
    try:
        from api_client import mos_content_get
        result = await mos_content_get(ctx, content_id)
        item = result.get("item") or None
        if item:
            return item
    except Exception:
        pass
    store_items = await _store_list(ctx)
    found = next((i for i in store_items if i.get("id") == content_id), None)
    if found:
        return found
    if content_id.isdigit():
        found = next((i for i in store_items if str(i.get("wp_post_id", "")) == content_id), None)
        if found:
            return found
    return None


async def create_content(ctx, data: dict) -> str:
    try:
        from api_client import mos_content_create
        result = await mos_content_create(ctx, data)
        item_id = result.get("id", "")
        if item_id:
            return item_id
    except Exception:
        pass
    try:
        doc = await ctx.store.create(CONTENT_COL, data)
        return doc.id
    except Exception:
        return ""


async def update_content(ctx, content_id: str, data: dict) -> None:
    try:
        from api_client import mos_content_update
        await mos_content_update(ctx, content_id, data)
        return
    except Exception:
        pass
    try:
        page = await ctx.store.query(CONTENT_COL, limit=200)
        docs = getattr(page, "data", None) or []
        doc = next((d for d in docs if getattr(d, "id", None) == content_id), None)
        if doc and isinstance(getattr(doc, "data", None), dict):
            merged = {**doc.data, **data}
            await ctx.store.update(CONTENT_COL, content_id, merged)
    except Exception:
        pass


async def delete_content(ctx, content_id: str) -> None:
    # Delete from BOTH stores — MOS returns OK even for non-existent IDs,
    # so we can't trust the response to know if it was in MOS or ctx.store.
    try:
        from api_client import mos_content_delete
        await mos_content_delete(ctx, content_id)
    except Exception:
        pass
    # Always also try ctx.store (handles legacy items)
    try:
        page = await ctx.store.query(CONTENT_COL, limit=200)
        docs = getattr(page, "data", None) or []
        doc = next((d for d in docs if getattr(d, "id", None) == content_id), None)
        if doc:
            await ctx.store.delete(CONTENT_COL, doc.id)
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

@ext.health_check
async def health_check(ctx):
    s = await load_settings(ctx)
    if not ser_ready(s) and not wp_ready(s):
        return {"status": "degraded", "reason": "No API keys configured — open Settings."}
    return {"status": "ok"}


def ser_ready(s: dict) -> bool:
    return bool(s.get("seranking_api_key") and s.get("seranking_domain"))

def wp_ready(s: dict) -> bool:
    return bool(s.get("wp_app_password"))

def gsc_ready(s: dict) -> bool:
    if not s.get("gsc_site_url"):
        return False
    return bool(
        s.get("gsc_credentials_json") or
        s.get("gsc_service_account") or
        (s.get("gsc_oauth_refresh_token") and s.get("gsc_oauth_client_id"))
    )
