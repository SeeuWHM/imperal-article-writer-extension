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

Every error dict this module returns carries an `error_code` (SDK
imperal_sdk.chat.error_codes taxonomy, or an app-declared code) — see
_err() below, the single place every handler builds its ActionResult.error
from. A code-less error gets stamped EXT_UNSTRUCTURED_ERROR by the kernel,
which is what P0-4 (structured error taxonomy) exists to prevent.
"""
from __future__ import annotations

import httpx

from imperal_sdk.types import ActionResult

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


def _err(data: dict) -> ActionResult:
    """The one place every handler builds an error ActionResult from a
    call_backend() result — always carries a structured code + retryable."""
    return ActionResult.error(
        error=data.get("error", "unknown error"),
        retryable=bool(data.get("_retryable", False)),
        code=data.get("error_code", "") or "INTERNAL",
    )


async def call_backend(ctx, method: str, path: str, params: dict | None = None,
                        json: dict | None = None, timeout: int = TIMEOUT) -> dict:
    """Call article-writer-api. Returns the parsed JSON body, or
    {"error": ..., "error_code": ..., "_retryable": bool}."""
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {
            "error": "Article Writer backend URL is not configured.",
            "error_code": "BACKEND_NOT_CONFIGURED", "_config": True,
        }

    backend_jwt = await ctx.secrets.get("backend_jwt")
    if not backend_jwt:
        return {
            "error": "Article Writer backend is not configured on our side yet — this has been logged.",
            "error_code": "BACKEND_NOT_CONFIGURED", "_config": True,
        }

    headers = {
        "Authorization": f"Bearer {backend_jwt}",
        "X-Imperal-Id": ctx.user.imperal_id,
    }

    url = f"{base_url}{path}"
    try:
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
            return {"error": f"Unsupported method {method}", "error_code": "INTERNAL", "_config": True}
    except httpx.TimeoutException:
        return {
            "error": "Article Writer backend timed out — please retry.",
            "error_code": "BACKEND_TIMEOUT", "_retryable": True,
        }
    except httpx.HTTPError as exc:
        return {
            "error": f"Article Writer backend is unreachable — this has been logged ({exc.__class__.__name__}).",
            "error_code": "BACKEND_5XX", "_retryable": True,
        }

    if resp.status_code == 401:
        return {
            "error": "Article Writer backend rejected our credentials — this has been logged.",
            "error_code": "PERMISSION_DENIED", "_config": True,
        }
    if resp.status_code == 404:
        return {"error": "Not found.", "error_code": "NOT_FOUND", "_config": True}
    if resp.status_code >= 500:
        detail = resp.body if isinstance(resp.body, dict) else {"detail": resp.body}
        msg = detail.get("detail", detail) if isinstance(detail, dict) else detail
        return {
            "error": f"Article Writer backend error: {msg}",
            "error_code": "BACKEND_5XX", "_retryable": True,
        }
    if resp.status_code >= 400:
        detail = resp.body if isinstance(resp.body, dict) else {"detail": resp.body}
        msg = detail.get("detail", detail) if isinstance(detail, dict) else detail
        return {"error": f"Article Writer error: {msg}", "error_code": "BACKEND_REJECTED"}

    return resp.body if isinstance(resp.body, dict) else {"data": resp.body}
