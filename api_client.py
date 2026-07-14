"""HTTP client — calls the shared article-writer-api backend microservice.

The backend base URL is a baked-in constant (app.py) — the public API
gateway host every extension on this platform calls, not a per-user secret.

Every call carries two things:
  - `backend_jwt`  (scope="app", write_mode="extension") — authenticates
                     THIS EXTENSION to article-writer-api. Developer-set
                     only via developer.save_app_secret; never entered or
                     seen by end users, never committed to source.
  - `X-Imperal-Id`  — the caller's own canonical platform identity
                     (ctx.user.imperal_id). The backend scopes every table
                     query to this value — there is no external per-user
                     API key involved (unlike SE Ranking's own account key),
                     since project/article ownership is by platform tenant.

Without a JWT, every call fails fast with a clear internal-config error
(never silently falls back — a missing platform secret is our bug, not the
user's).
"""
from __future__ import annotations

from app import SERVER_URL

TIMEOUT = 30
GENERATE_TIMEOUT = 15  # generation itself runs as a background job — this just enqueues it
PATCH_TIMEOUT = 60     # patch runs synchronously (locate + one-section rewrite)


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


async def call_backend(ctx, method: str, path: str, params: dict | None = None,
                        json: dict | None = None, timeout: int = TIMEOUT) -> dict:
    """Call article-writer-api. Returns the parsed JSON body, or {"error": ...}."""
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Article Writer backend URL is not configured.", "_config": True}

    backend_jwt = await ctx.secrets.get("backend_jwt")
    if not backend_jwt:
        return {
            "error": "Article Writer backend is not configured on our side yet — this has been logged.",
            "_config": True,
        }

    headers = {
        "Authorization": f"Bearer {backend_jwt}",
        "X-Imperal-Id": ctx.user.imperal_id,
    }

    url = f"{base_url}{path}"
    if method.upper() == "GET":
        resp = await ctx.http.get(url, params=params or {}, headers=headers, timeout=timeout)
    elif method.upper() == "POST":
        resp = await ctx.http.post(url, params=params or {}, json=json or {}, headers=headers, timeout=timeout)
    elif method.upper() == "PATCH":
        resp = await ctx.http.patch(url, params=params or {}, json=json or {}, headers=headers, timeout=timeout)
    elif method.upper() == "PUT":
        resp = await ctx.http.put(url, params=params or {}, json=json or {}, headers=headers, timeout=timeout)
    elif method.upper() == "DELETE":
        resp = await ctx.http.delete(url, params=params or {}, headers=headers, timeout=timeout)
    else:
        return {"error": f"Unsupported method {method}", "_config": True}

    if resp.status_code == 401:
        return {"error": "Article Writer backend rejected our credentials — this has been logged.", "_config": True}
    if resp.status_code == 404:
        return {"error": "Not found.", "_config": True}
    if resp.status_code >= 400:
        detail = resp.body if isinstance(resp.body, dict) else {"detail": resp.body}
        msg = detail.get("detail", detail) if isinstance(detail, dict) else detail
        return {"error": f"Article Writer error: {msg}", "_config": False}

    return resp.body if isinstance(resp.body, dict) else {"data": resp.body}
