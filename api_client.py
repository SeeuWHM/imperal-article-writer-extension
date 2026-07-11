"""MOS server HTTP client — all external API calls go through here."""
from __future__ import annotations

import os
import time

from wpb_app import load_settings, gsc_ready

SERVER_URL = os.environ.get("ARTICLE_WRITER_BACKEND_URL", "")
SERVER_API_KEY = os.environ.get("ARTICLE_WRITER_BACKEND_API_KEY", "")
TIMEOUT = 30
TIMEOUT_PLAN = 120  # content plan: 3 parallel API calls + AI generation


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def _bearer_headers() -> dict:
    token = (SERVER_API_KEY or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def log_action(ctx, action: str, content_id: str, duration_ms: int,
                     success: bool, error: str = "") -> None:
    """Fire-and-forget: POST action log to MOS. Never raises."""
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return
    try:
        await ctx.http.post(
            f"{base_url}/api/logs/action",
            json={
                "action": action,
                "content_id": content_id or "",
                "duration_ms": duration_ms,
                "success": success,
                "error": error,
                "timestamp": time.time(),
            },
            headers=_bearer_headers(),
            timeout=5,
        )
    except Exception:
        pass  # logging must never break the action


async def _post(ctx, endpoint: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Article Writer backend URL is not configured."}
    resp = await ctx.http.post(
        f"{base_url}{endpoint}",
        json=payload,
        headers=_bearer_headers(),
        timeout=timeout,
    )
    if not resp.ok:
        try:
            body = resp.text()[:200]
        except Exception:
            body = ""
        return {"error": f"Server error {resp.status_code}: {body}"}
    return resp.json()


async def _get(ctx, endpoint: str, timeout: int = TIMEOUT) -> dict:
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Article Writer backend URL is not configured."}
    resp = await ctx.http.get(
        f"{base_url}{endpoint}",
        headers=_bearer_headers(),
        timeout=timeout,
    )
    if not resp.ok:
        try:
            body = resp.text()[:200]
        except Exception:
            body = ""
        return {"error": f"Server error {resp.status_code}: {body}"}
    return resp.json()


async def ser_keywords(ctx, domain: str, source: str, limit: int, min_volume: int, max_difficulty: int) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    if not key:
        return {"error": "SE Ranking API key not configured. Go to Settings."}
    return await _post(ctx, "/api/seranking/keywords", {
        "seranking_api_key": key,
        "domain": domain,
        "source": source,
        "limit": limit,
        "min_volume": min_volume,
        "max_difficulty": max_difficulty,
    })


async def ser_gaps(ctx, domain: str, competitor: str, source: str, limit: int) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    if not key:
        return {"error": "SE Ranking API key not configured. Go to Settings."}
    return await _post(ctx, "/api/seranking/gaps", {
        "seranking_api_key": key,
        "domain": domain,
        "competitor": competitor,
        "source": source,
        "limit": limit,
    })


async def fetch_ai_traffic(ctx) -> dict:
    """Fetch AI referrer traffic via Matomo Analytics extension IPC."""
    try:
        result = await ctx.extensions.call("analytics", "ai_referrers", period="month")
        if result and not getattr(result, "error", None):
            data = getattr(result, "data", {}) or {}
            if data.get("sources") is not None:
                return data
    except Exception:
        pass
    return {"sources": [], "total_visits": 0, "prev_total_visits": 0, "total_change_pct": 0}


async def ser_rankings(ctx) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    project_id = s.get("seranking_project_id", "")
    if not key:
        return {"error": "SE Ranking API key not configured. Go to Settings."}
    if not project_id:
        return {"error": "SE Ranking Project ID not configured. Go to Settings."}
    return await _post(ctx, "/api/seranking/rankings", {
        "seranking_api_key": key,
        "project_id": project_id,
    })


async def ser_projects(ctx) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    if not key:
        return {"error": "SE Ranking API key not configured. Go to Settings."}
    return await _post(ctx, "/api/seranking/projects", {
        "seranking_api_key": key,
    })


async def content_plan(ctx, competitor: str = "", language: str = "en",
                       existing_keywords: list = None) -> dict:
    s = await load_settings(ctx)

    # Growing pages via Matomo Analytics extension IPC only
    growing_pages = []
    matomo_url = matomo_token = ""
    matomo_site_id = 1
    try:
        result = await ctx.extensions.call("analytics", "growing_pages", limit=20)
        if result and not getattr(result, "error", None):
            data = getattr(result, "data", {}) or {}
            growing_pages = data.get("pages", [])
    except Exception:
        pass

    if not growing_pages:
        # Get Matomo config from analytics extension IPC
        try:
            mc = await ctx.extensions.call("analytics", "matomo_config")
            if mc and not getattr(mc, "error", None):
                d = getattr(mc, "data", {}) or {}
                if d.get("configured"):
                    matomo_url     = d.get("matomo_url", "")
                    matomo_token   = d.get("matomo_token", "")
                    matomo_site_id = d.get("matomo_site_id", 1)
        except Exception:
            pass

    return await _post(ctx, "/api/content/plan", {
        "user_key":      "",
        "seranking_key": s.get("seranking_api_key", ""),
        "domain":        s.get("seranking_domain", ""),
        "source":        s.get("seranking_source", "us"),
        "competitor":    competitor or s.get("seranking_competitor", ""),
        "language":      language,
        "profile_name":  s.get("active_profile", ""),
        "wp_url":        s.get("wp_url", ""),
        "wp_user":       s.get("wp_username", ""),
        "wp_password":   s.get("wp_app_password", ""),
        # Matomo — used only if analytics extension not installed
        "matomo_url":    matomo_url,
        "matomo_token":  matomo_token,
        "matomo_site_id": matomo_site_id,
        # Pre-fetched from analytics IPC (skips Matomo fetch on server)
        "growing_pages": growing_pages,
        # Existing keywords from extension store (avoid duplicates in plan + WP)
        "existing_plan_keywords": existing_keywords or [],
    }, timeout=TIMEOUT_PLAN)


async def generate_brief(ctx, keyword: str, content_type: str = "blog",
                         volume: int = 0, difficulty: int = 0,
                         extra: str = "", language: str = "en") -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/content/brief", {
        "keyword":      keyword,
        "content_type": content_type,
        "volume":       volume,
        "difficulty":   difficulty,
        "extra":        extra,
        "language":     language,
    }, timeout=25)


async def generate_newsletter_mos(ctx, news_text: str, tone_note: str = "") -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/content/newsletter", {
        "news_text":         news_text,
        "tone_note":         tone_note,
        "company_name":      s.get("company_name", ""),
        "brand_description": s.get("brand_description", ""),
        "brand_voice":       s.get("brand_voice", ""),
        "newsletter_cta":    s.get("newsletter_cta", ""),
        "site_url":          s.get("site_url", ""),
        "blog_url":          s.get("blog_url", ""),
        "tg_url":            s.get("tg_url", ""),
        "language":          s.get("language", "en"),
    }, timeout=60)


async def keywords_for_article(ctx, keyword: str) -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/content/keywords_for_article", {
        "seranking_key": s.get("seranking_api_key", ""),
        "domain":        s.get("seranking_domain", ""),
        "keyword":       keyword,
        "language":      s.get("language", "en"),
    }, timeout=60)


def _article_payload(s: dict, topic: str, keyword: str, article_type: str,
                     word_count: int, language: str, secondary_keywords: list,
                     lsi_terms: list, questions: list,
                     brand_context: str, ser_context: str) -> dict:
    return {
        "user_key":           "",
        "topic":              topic,
        "keyword":            keyword,
        "language":           language,
        "word_count":         word_count,
        "article_type":       article_type,
        "secondary_keywords": secondary_keywords or [],
        "lsi_terms":          lsi_terms or [],
        "questions":          questions or [],
        "brand_voice":        s.get("brand_voice", ""),
        "company_name":       s.get("company_name", ""),
        "brand_description":  s.get("brand_description", ""),
        "site_url":           s.get("site_url", ""),
        "blog_url":           s.get("blog_url", ""),
        "brand_context":      brand_context,
        "ser_context":        ser_context,
    }


async def generate_article(ctx, topic: str, keyword: str, article_type: str = "blog",
                            word_count: int = 1500, language: str = "en",
                            secondary_keywords: list = None, lsi_terms: list = None,
                            questions: list = None,
                            brand_context: str = "", ser_context: str = "") -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/content/generate",
                       _article_payload(s, topic, keyword, article_type, word_count, language,
                                        secondary_keywords, lsi_terms, questions,
                                        brand_context, ser_context),
                       timeout=120)


async def start_generate_article(ctx, topic: str, keyword: str, article_type: str = "blog",
                                  word_count: int = 1500, language: str = "en",
                                  secondary_keywords: list = None, lsi_terms: list = None,
                                  questions: list = None,
                                  brand_context: str = "", ser_context: str = "") -> dict:
    """Start background article generation. Returns {job_id, status: 'pending'} immediately."""
    s = await load_settings(ctx)
    return await _post(ctx, "/api/content/generate/start",
                       _article_payload(s, topic, keyword, article_type, word_count, language,
                                        secondary_keywords, lsi_terms, questions,
                                        brand_context, ser_context),
                       timeout=10)


async def poll_article_job(ctx, job_id: str) -> dict:
    """Poll job status. Returns {status: pending|done|error|not_found, result?: {...}}"""
    return await _get(ctx, f"/api/content/jobs/{job_id}", timeout=10)


async def start_refine_article(ctx, content: str, keyword: str, instruction: str = "") -> dict:
    """Start background article improvement. Returns {job_id, status: 'pending'} immediately."""
    return await _post(ctx, "/api/content/refine/start", {
        "user_key":    "",
        "content":     content,
        "keyword":     keyword,
        "instruction": instruction,
    }, timeout=10)


async def wp_publish(ctx, title: str, content: str, status: str = "draft") -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/wordpress/publish", {
        "wp_url": s.get("wp_url", ""),
        "wp_user": s.get("wp_username", ""),
        "wp_password": s.get("wp_app_password", ""),
        "title": title,
        "content": content,
        "status": status,
    })


async def wp_update(ctx, post_id: int, title: str = "", content: str = "", status: str = "") -> dict:
    s = await load_settings(ctx)
    return await _post(ctx, "/api/wordpress/update", {
        "wp_url": s.get("wp_url", ""),
        "wp_user": s.get("wp_username", ""),
        "wp_password": s.get("wp_app_password", ""),
        "post_id": post_id,
        "title": title,
        "content": content,
        "status": status,
    })


# ── MOS Storage — user-isolated content + docs ────────────────────────────────

def _scope(ctx) -> dict:
    """User context for storage isolation — (tenant_id, user_id) composite key."""
    return {
        "user_id": ctx.user.imperal_id,
        "tenant_id": ctx.user.tenant_id,
    }


async def mos_content_list(ctx) -> list:
    data = await _post(ctx, "/api/storage/content/list", _scope(ctx))
    return data.get("items", [])


async def mos_content_get(ctx, item_id: str) -> dict:
    return await _post(ctx, "/api/storage/content/get", {**_scope(ctx), "id": item_id})


async def mos_content_create(ctx, item: dict) -> dict:
    return await _post(ctx, "/api/storage/content/create", {**_scope(ctx), **item})


async def mos_content_update(ctx, item_id: str, fields: dict) -> dict:
    return await _post(ctx, "/api/storage/content/update", {**_scope(ctx), "id": item_id, **fields})


async def mos_content_delete(ctx, item_id: str) -> dict:
    return await _post(ctx, "/api/storage/content/delete", {**_scope(ctx), "id": item_id})


async def mos_docs_list(ctx) -> list:
    data = await _post(ctx, "/api/storage/docs/list", _scope(ctx))
    return data.get("docs", [])


async def mos_docs_get_all(ctx) -> list:
    """Returns docs with full content — for AI context injection."""
    data = await _post(ctx, "/api/storage/docs/get_all", _scope(ctx))
    return data.get("docs", [])


async def mos_docs_create(ctx, name: str, content: str, size: int = 0, ext: str = "md") -> dict:
    return await _post(ctx, "/api/storage/docs/create", {
        **_scope(ctx), "name": name, "content": content, "size": size, "ext": ext,
    })


async def mos_docs_delete(ctx, doc_id: str) -> dict:
    return await _post(ctx, "/api/storage/docs/delete", {**_scope(ctx), "id": doc_id})


async def ser_add_keyword(ctx, keyword: str, landing_url: str = "") -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    pid = s.get("seranking_project_id", "")
    if not key or not pid:
        return {"error": "SE Ranking API key / project ID not configured."}
    return await _post(ctx, "/api/seranking/add-keyword", {
        "seranking_api_key": key, "project_id": pid,
        "keyword": keyword, "landing_url": landing_url,
    })


async def ser_remove_keyword(ctx, keyword_id: str) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    pid = s.get("seranking_project_id", "")
    if not key or not pid:
        return {"error": "SE Ranking API key / project ID not configured."}
    return await _post(ctx, "/api/seranking/remove-keyword", {
        "seranking_api_key": key, "project_id": pid, "keyword_id": keyword_id,
    })


async def ser_list_site_keywords(ctx) -> dict:
    s = await load_settings(ctx)
    key = s.get("seranking_api_key", "")
    pid = s.get("seranking_project_id", "")
    if not key or not pid:
        return {"error": "SE Ranking API key / project ID not configured."}
    return await _post(ctx, "/api/seranking/list-site-keywords", {
        "seranking_api_key": key, "project_id": pid,
    })


# ── Google Search Console ──────────────────────────────────────────────────────

def _gsc_auth_payload(s: dict) -> dict:
    """Build auth fields for GSC API call. Supports smart JSON, SA JSON, OAuth2."""
    base = {"site_url": s.get("gsc_site_url", "")}
    if s.get("gsc_credentials_json"):
        base["credentials_json"] = s["gsc_credentials_json"]
    elif s.get("gsc_service_account"):
        base["service_account_json"] = s["gsc_service_account"]
    elif s.get("gsc_oauth_refresh_token"):
        base["oauth_client_id"] = s.get("gsc_oauth_client_id", "")
        base["oauth_client_secret"] = s.get("gsc_oauth_client_secret", "")
        base["oauth_refresh_token"] = s["gsc_oauth_refresh_token"]
    return base


async def gsc_verify(ctx) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {"ok": False, "error": "GSC not configured"}
    return await _post(ctx, "/api/gsc/verify", _gsc_auth_payload(s))


async def gsc_pages(ctx) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {"pages": []}
    return await _post(ctx, "/api/gsc/pages", _gsc_auth_payload(s))


async def gsc_page_detail(ctx, page_url: str) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {}
    return await _post(ctx, "/api/gsc/page-detail", {**_gsc_auth_payload(s), "page_url": page_url})


async def gsc_top_queries(ctx) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {"queries": []}
    return await _post(ctx, "/api/gsc/top-queries", _gsc_auth_payload(s))


async def gsc_anomalies(ctx) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {"anomalies": []}
    return await _post(ctx, "/api/gsc/anomalies", _gsc_auth_payload(s))


async def gsc_growth_opportunities(ctx) -> dict:
    s = await load_settings(ctx)
    if not gsc_ready(s):
        return {"opportunities": []}
    return await _post(ctx, "/api/gsc/growth-opportunities", _gsc_auth_payload(s))
