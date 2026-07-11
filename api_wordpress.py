"""WordPress REST API client.

Base URL : https://blog.webhostmost.com/wp-json/wp/v2
Auth     : Application Password — Basic base64(username:app_password)
           Generate in WP Admin → Users → Profile → Application Passwords
"""
from __future__ import annotations

import base64


def _headers(username: str, app_password: str) -> dict:
    token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _base(wp_url: str) -> str:
    return wp_url.rstrip("/") + "/wp-json/wp/v2"


def _unwrap(resp):
    """ctx.http returns HTTP response objects in some SDK versions. Unwrap to JSON."""
    if hasattr(resp, "json"):
        try:
            return resp.json() if callable(resp.json) else resp.json
        except Exception:
            return {}
    return resp


# ── Posts ─────────────────────────────────────────────────────────────────────

async def create_post(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
    title: str,
    content: str,
    status: str = "draft",
    author_id: int = 3,
    categories: list[int] | None = None,
    tags: list[int] | None = None,
) -> dict:
    """Create a new WordPress post. Returns the created post object."""
    payload: dict = {
        "title": title,
        "content": content,
        "status": status,
        "author": author_id,
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags

    resp = await ctx.http.post(
        f"{_base(wp_url)}/posts",
        headers=_headers(username, app_password),
        json=payload,
    )
    return _parse_post(_unwrap(resp))


async def update_post(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
    post_id: int,
    **fields,
) -> dict:
    """Update an existing WP post (title, content, status, etc.)."""
    resp = await ctx.http.patch(
        f"{_base(wp_url)}/posts/{post_id}",
        headers=_headers(username, app_password),
        json={k: v for k, v in fields.items() if v is not None},
    )
    return _parse_post(_unwrap(resp))


async def list_posts(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
    per_page: int = 10,
    status: str = "draft,publish",
) -> list[dict]:
    """List recent posts."""
    resp = await ctx.http.get(
        f"{_base(wp_url)}/posts",
        headers=_headers(username, app_password),
        params={"per_page": per_page, "status": status, "orderby": "date", "order": "desc"},
    )
    data = _unwrap(resp)
    if isinstance(data, list):
        return [_parse_post(p) for p in data]
    return []


async def verify_connection(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
) -> bool:
    """Verify WP credentials by requesting the current user endpoint."""
    try:
        resp = await ctx.http.get(
            f"{_base(wp_url)}/users/me",
            headers=_headers(username, app_password),
        )
        data = _unwrap(resp)
        return isinstance(data, dict) and bool(data.get("id"))
    except Exception:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_post(resp) -> dict:
    if not isinstance(resp, dict):
        return {}
    if resp.get("code") and not resp.get("id"):
        return {"_wp_error": resp.get("message", str(resp))}
    title = resp.get("title", {})
    content = resp.get("content", {})
    return {
        "id": resp.get("id"),
        "status": resp.get("status"),
        "title": title.get("rendered", title) if isinstance(title, dict) else title,
        "link": resp.get("link", ""),
        "date": resp.get("date", ""),
    }


async def get_post(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
    post_id: int,
) -> dict:
    """Fetch a single post with full content."""
    resp = await ctx.http.get(
        f"{_base(wp_url)}/posts/{post_id}",
        headers=_headers(username, app_password),
    )
    data = _unwrap(resp)
    if not isinstance(data, dict) or data.get("_wp_error"):
        return data or {}
    title = data.get("title", {})
    content = data.get("content", {})
    excerpt = data.get("excerpt", {})
    return {
        "id": data.get("id"),
        "status": data.get("status"),
        "title": title.get("rendered", "") if isinstance(title, dict) else title,
        "content": content.get("rendered", "") if isinstance(content, dict) else content,
        "excerpt": excerpt.get("rendered", "") if isinstance(excerpt, dict) else excerpt,
        "link": data.get("link", ""),
        "date": data.get("date", ""),
        "slug": data.get("slug", ""),
    }


async def search_posts(
    ctx,
    wp_url: str,
    username: str,
    app_password: str,
    query: str,
    per_page: int = 5,
) -> list[dict]:
    """Search posts by title keyword."""
    resp = await ctx.http.get(
        f"{_base(wp_url)}/posts",
        headers=_headers(username, app_password),
        params={"search": query, "per_page": per_page, "status": "draft,publish"},
    )
    data = _unwrap(resp)
    if isinstance(data, list):
        return [_parse_post(p) for p in data]
    return []
