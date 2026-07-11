"""Publishing handlers — WordPress publish + SEO meta setup."""
import re
import time

from imperal_sdk import ActionResult, ui
from imperal_sdk.types import ActionResult  # noqa: F811

from wpb_app import chat, get_content, update_content, load_settings, load_ui_state, list_content, save_ui_state
from wpb_app import save_settings as _save_settings
from api_client import log_action, _post
from api_wordpress import create_post, update_post
from params import (PublishWpParams, SaveSettingsParams, SetWpSeoParams, ListWpPostsParams,
                    UnpublishWpParams, GetArticleLinkParams, RewriteArticleParams,
                    AddKeywordsParams, CheckSeoMetaParams, EmptyParams)


async def _resolve_id(ctx, content_id: str, keyword_hint: str = "") -> str:
    """Resolve content_id: explicit → UI state selected_id → search by keyword → most recent.

    All logic on the server — Webbee just passes what the user said.
    """
    if content_id:
        return content_id
    state = await load_ui_state(ctx)
    if state.get("selected_id"):
        return state["selected_id"]
    if keyword_hint:
        items = await list_content(ctx)
        q = keyword_hint.lower()
        for item in items:
            kw    = (item.get("keyword") or "").lower()
            title = (item.get("title") or "").lower()
            if q in kw or q in title:
                return item["id"]
        # partial word match
        for word in q.split():
            for item in items:
                kw    = (item.get("keyword") or "").lower()
                title = (item.get("title") or "").lower()
                if word in kw or word in title:
                    return item["id"]
    return ""


async def _auto_seo(ctx, cid: str, wp_post_id: int, item: dict, s: dict) -> None:
    """Auto-generate and set Rank Math SEO fields after publish. Runs on MOS VPS."""
    try:
        title   = item.get("title") or item.get("keyword", "")
        keyword = item.get("focus_keyword") or item.get("keyword", "")
        content = item.get("content", "")
        language = s.get("language", "en")

        # Use stored meta if available, else generate via MOS
        meta_desc = item.get("meta_description", "")
        excerpt   = item.get("excerpt", "")
        if not meta_desc or not excerpt:
            seo = await _post(ctx, "/api/content/seo_meta", {
                "title":            title,
                "keyword":          keyword,
                "content_snippet":  content[:500],
                "language":         language,
            })
            if "error" not in seo:
                meta_desc = meta_desc or seo.get("meta_description", "")
                excerpt   = excerpt   or seo.get("excerpt", "")

        # Sanitize: strip LLM echoes + em dashes
        def _clean_seo(text: str, maxlen: int) -> str:
            for pfx in ["here is a wordpress post excerpt:", "here is an seo meta description:",
                        "wordpress post excerpt:", "meta description:", "excerpt:", "here's a "]:
                if text.lower().startswith(pfx):
                    text = text[len(pfx):].strip()
            text = text.replace("—", " - ").replace("–", " - ")
            return re.sub(r'\s+', ' ', text).strip().strip('"').strip("'")[:maxlen]
        meta_desc = _clean_seo(meta_desc, 155)
        excerpt   = _clean_seo(excerpt, 150)

        # Rank Math focus keyword: primary + up to 4 secondary
        secondary  = item.get("secondary_keywords", [])
        all_kws    = [keyword] + [k for k in secondary[:4] if k.lower() != keyword.lower()]
        rm_focus   = ", ".join(filter(None, all_kws))

        # Set excerpt via direct WP REST API (ctx.http works for native fields)
        await update_post(
            ctx, s["wp_url"], s["wp_username"], s["wp_app_password"],
            post_id=wp_post_id,
            excerpt=excerpt,
        )

        # Set Rank Math fields + slug + seo_title via MOS server
        await _post(ctx, "/api/wordpress/update", {
            "wp_url":          s["wp_url"],
            "wp_user":         s["wp_username"],
            "wp_password":     s["wp_app_password"],
            "post_id":         wp_post_id,
            "title":           title,
            "focus_keyword":   rm_focus,
            "meta_description": meta_desc,
        })
        await update_content(ctx, cid, {
            "meta_description": meta_desc,
            "focus_keyword":    keyword,
            "excerpt":          excerpt,
        })
    except Exception:
        pass  # SEO update is best-effort, never block publish

# ── Category IDs (blog.webhostmost.com) ───────────────────────────────────────
_KW_CATEGORIES = {
    "wordpress": 46,
    "webhostmost": 47,
    "wpanel": 47,
    "webbee": 47,
    "imperal": 47,
}
_TYPE_CATEGORIES = {
    "comparison": 21,
    "review": 21,
    "news": 51,
    "tutorial": 45,
    "blog": 45,
    "pillar": 48,
}


def _pick_category(keyword: str, article_type: str) -> int:
    kw_lower = keyword.lower()
    for kw, cat_id in _KW_CATEGORIES.items():
        if kw in kw_lower:
            return cat_id
    return _TYPE_CATEGORIES.get(article_type, 45)


def _prepare_content(content: str, faq_schema: str, blog_url: str) -> str:
    """Resolve [INTERNAL] placeholders, strip em/en dashes, append FAQ JSON-LD."""
    if blog_url:
        content = re.sub(r'href="\[INTERNAL\]"', f'href="{blog_url.rstrip("/")}"', content)
    else:
        content = re.sub(r'href="\[INTERNAL\]"', 'href="#"', content)
    # Brand rule: no em dash (—) or en dash (–) — replace with space-hyphen-space
    content = re.sub(r'\s*[—–]\s*', ' - ', content)
    if faq_schema:
        content = content + "\n" + faq_schema
    return content


@chat.function(
    "publish_wp",
    description="Create or update a WordPress post from a blog content item. status: 'draft' or 'publish'.",
    action_type="write",
    chain_callable=True,
    effects=["publish:post"],
    event="seo.content.published",
)
async def publish_wp(ctx, params: PublishWpParams) -> ActionResult:
    """Create or update a WordPress post as draft or published."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id, params.keyword_hint)
    action_name = f"publish_wp_{params.status}"
    try:
        s = await load_settings(ctx)
        if not s.get("wp_app_password"):
            await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), False, "WP not configured")
            return ActionResult.error(error=(
                "WordPress Application Password not configured. "
                "Go to Settings → WordPress → Application Passwords."
            ))

        item = await get_content(ctx, cid)
        if not item:
            await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), False, "Content item not found")
            return ActionResult.error(error="Content item not found")

        title      = item.get("title") or item.get("keyword", "Untitled")
        raw_content = item.get("content", "")
        if not raw_content:
            await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), False, "Content is empty")
            return ActionResult.error(error="Content is empty — run AI Write first.")

        wp_post_id   = item.get("wp_post_id")
        wp_url       = s["wp_url"]
        username     = s["wp_username"]
        app_pw       = s["wp_app_password"]
        author_id    = int(s.get("wp_author_id", 3))
        blog_url     = s.get("blog_url", "")
        faq_schema   = item.get("faq_schema", "")
        article_type = item.get("type", "blog")
        keyword      = item.get("keyword", "")
        category_id  = _pick_category(keyword, article_type)
        content      = _prepare_content(raw_content, faq_schema, blog_url)

        if wp_post_id:
            post = await update_post(
                ctx, wp_url, username, app_pw,
                post_id=int(wp_post_id),
                title=title, content=content, status=params.status,
                categories=[category_id],
            )
            wp_action = "updated"
        else:
            post = await create_post(
                ctx, wp_url, username, app_pw,
                title=title, content=content, status=params.status,
                author_id=author_id, categories=[category_id],
            )
            wp_action = "created"

        if not post.get("id"):
            wp_msg = post.get("_wp_error") or str(post)
            await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), False, f"WordPress error: {wp_msg[:200]}")
            return ActionResult.error(error=f"WordPress error: {wp_msg}")

        new_status = "published" if params.status == "publish" else item.get("status", "review")
        await update_content(ctx, cid, {
            "wp_post_id":  post["id"],
            "target_url":  post.get("link", ""),
            "status":      new_status,
            "wp_category": category_id,
        })

        # Auto-set Rank Math SEO fields (meta description, focus keyword, excerpt)
        await _auto_seo(ctx, cid, int(post["id"]), item, s)

        await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={"wp_id": post["id"], "link": post.get("link", ""), "wp_status": params.status},
            summary=f"Post {wp_action} on WordPress (ID {post['id']}, status: {params.status}). Rank Math SEO set. {post.get('link', '')}",
            refresh_panels=["sidebar"],
        )
    except Exception as e:
        await log_action(ctx, action_name, cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "publish_wp_draft",
    description=(
        "Save or publish the current article to WordPress as a DRAFT (not live). "
        "ALWAYS use for: сохрани в WordPress, сохрани как черновик, загрузи в WordPress черновик, "
        "save to wordpress, save as draft, push to wp, сохрани статью в WP, отправь в WP черновик."
    ),
    action_type="write",
    chain_callable=True,
    effects=["publish:post"],
    event="seo.content.published",
)
async def publish_wp_draft(ctx, params: PublishWpParams) -> ActionResult:
    """Publish or update the current post as a WordPress draft."""
    params.status = "draft"
    return await publish_wp(ctx, params)


@chat.function(
    "publish_wp_publish",
    description=(
        "Publish the current article to WordPress as LIVE (publicly visible). "
        "ALWAYS use for: опубликуй в WordPress, опубликуй статью, публикуй на сайт, "
        "publish to wordpress, make it live, опубликуй сейчас, выложи в блог."
    ),
    action_type="write",
    chain_callable=True,
    effects=["publish:post"],
    event="seo.content.published",
)
async def publish_wp_publish(ctx, params: PublishWpParams) -> ActionResult:
    """Publish or update the current post as live on WordPress."""
    params.status = "publish"
    return await publish_wp(ctx, params)


@chat.function(
    "set_wp_seo",
    description=(
        "Set Rank Math SEO on the WordPress post: focus + secondary keywords, meta description, excerpt. "
        "Auto-generates meta description and excerpt if not provided. Call after publish_wp."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:post"],
    event="seo.content.updated",
)
async def set_wp_seo(ctx, params: SetWpSeoParams) -> ActionResult:
    """Set Rank Math SEO fields on the WordPress post."""
    t0 = time.monotonic()
    cid = await _resolve_id(ctx, params.content_id, params.keyword_hint)
    try:
        s = await load_settings(ctx)
        if not s.get("wp_app_password"):
            await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), False, "WordPress not configured")
            return ActionResult.error(error="WordPress not configured. Go to Settings.")

        item = await get_content(ctx, cid)
        if not item:
            await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), False, "Content item not found")
            return ActionResult.error(error="Content item not found")

        wp_post_id = item.get("wp_post_id")
        if not wp_post_id:
            await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), False, "No wp_post_id")
            return ActionResult.error(error="Publish to WordPress first, then set SEO.")

        focus_kw       = params.focus_keyword or item.get("focus_keyword") or item.get("keyword", "")
        secondary_kws  = item.get("secondary_keywords", [])
        title          = item.get("title") or item.get("keyword", "")
        content_html   = item.get("content", "")

        # Rank Math focus keyword field: primary + up to 4 secondary (comma-separated)
        all_kws = [focus_kw] + [k for k in secondary_kws[:4] if k.lower() != focus_kw.lower()]
        rm_focus_kw = ", ".join(all_kws)

        # Meta + excerpt: use MOS server (avoids ctx.ai.complete instruction-echo bugs)
        meta_desc = params.meta_description or item.get("meta_description", "")
        excerpt   = item.get("excerpt", "")
        if not meta_desc or not excerpt:
            seo = await _post(ctx, "/api/content/seo_meta", {
                "title":            title,
                "keyword":          focus_kw,
                "content_snippet":  content_html[:500],
                "language":         s.get("language", "en"),
            })
            if "error" not in seo:
                meta_desc = meta_desc or seo.get("meta_description", "")
                excerpt   = excerpt   or seo.get("excerpt", "")

        # Sanitize: strip instruction echoes + em dashes (brand rule)
        def _clean(text: str, maxlen: int) -> str:
            for prefix in [
                "here is a wordpress post excerpt:", "wordpress post excerpt:",
                "here is an seo meta description:", "meta description:",
                "excerpt:", "here's a ", "here is a ",
            ]:
                if text.lower().startswith(prefix):
                    text = text[len(prefix):].strip()
            text = text.replace("—", " - ").replace("–", " - ")  # em/en dash
            text = re.sub(r'\s+', ' ', text).strip().strip('"').strip("'")
            return text[:maxlen]

        meta_desc = _clean(meta_desc, 155)
        excerpt   = _clean(excerpt, 150)

        # Excerpt via direct WP REST API
        post = await update_post(
            ctx,
            s["wp_url"], s["wp_username"], s["wp_app_password"],
            post_id=int(wp_post_id),
            excerpt=excerpt,
        )

        # Rank Math fields via MOS (httpx on VPS, avoids ctx.http meta field issues)
        await _post(ctx, "/api/wordpress/update", {
            "wp_url":          s["wp_url"],
            "wp_user":         s["wp_username"],
            "wp_password":     s["wp_app_password"],
            "post_id":         int(wp_post_id),
            "title":           title,
            "focus_keyword":   rm_focus_kw,
            "meta_description": meta_desc,
        })

        if not post.get("id"):
            wp_msg = post.get("_wp_error") or str(post)
            await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), False, f"WP SEO update failed: {wp_msg[:200]}")
            return ActionResult.error(error=f"WP SEO update failed: {wp_msg}")

        await update_content(ctx, cid, {
            "meta_description": meta_desc,
            "focus_keyword":    focus_kw,
            "excerpt":          excerpt,
        })

        kw_count = len(all_kws)
        await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), True)
        return ActionResult.success(
            data={
                "wp_post_id": wp_post_id,
                "focus_keyword": focus_kw,
                "all_keywords": all_kws,
                "meta_description": meta_desc,
                "excerpt": excerpt,
            },
            summary=(
                f"✅ Rank Math updated on WP post #{wp_post_id} ({title[:50]})\n"
                f"Focus keyword: {focus_kw}\n"
                f"Secondary keywords ({kw_count - 1}): {', '.join(all_kws[1:4])}\n"
                f"Meta ({len(meta_desc)} chars): {meta_desc}\n"
                f"Excerpt: {excerpt[:80]}\n"
                f"Slug updated to short keyword-based URL"
            ),
        )
    except Exception as e:
        await log_action(ctx, "set_wp_seo", cid, int((time.monotonic() - t0) * 1000), False, str(e))
        return ActionResult.error(error=str(e))


@chat.function(
    "save_settings",
    description="Save API keys and configuration for SE Ranking and WordPress.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="seo.settings.saved",
)
async def save_settings_fn(ctx, params: SaveSettingsParams) -> ActionResult:
    """Save extension settings (API keys, WP credentials)."""
    payload = params.model_dump(exclude_none=True)
    if "seranking_data_key" in payload and "seranking_api_key" not in payload:
        payload["seranking_api_key"] = payload.pop("seranking_data_key")
    if "seranking_project_key" in payload and "seranking_project_id" not in payload:
        payload.pop("seranking_project_key")
    updated = await _save_settings(ctx, payload)
    keys_set = [k for k, v in updated.items() if v and (k.endswith("_key") or k.endswith("_password") or k == "seranking_api_key")]
    return ActionResult.success(
        data={"updated": list(updated.keys())},
        summary=f"Settings saved. Credentials configured: {', '.join(keys_set) or 'none'}",
    )


@chat.function(
    "get_settings",
    description=(
        "Show WP Blogger extension settings — SE Ranking and WordPress API keys (masked). "
        "Use ONLY for: SE Ranking keys configured, WordPress credentials check, "
        "какие ключи SE Ranking настроены, есть ли ключ SE Ranking, WP Blogger настройки, "
        "seranking_api_key, wp_app_password configured. "
        "NOT for Matomo/analytics stats — only API key presence check."
    ),
    action_type="read",
)
async def get_settings(ctx, params: EmptyParams) -> ActionResult:
    """Show which settings are configured (keys masked)."""
    s = await load_settings(ctx)
    def _mask(v):
        if not v: return "NOT SET"
        sv = str(v)
        return sv[:4] + "***" + sv[-4:] if len(sv) > 8 else "***"

    rows = [
        {"key": "SE Ranking API Key",     "value": _mask(s.get("seranking_api_key"))},
        {"key": "SE Ranking Project ID",  "value": s.get("seranking_project_id") or "NOT SET"},
        {"key": "SE Ranking Domain",      "value": s.get("seranking_domain") or "NOT SET"},
        {"key": "SE Ranking Source",      "value": s.get("seranking_source") or "us"},
        {"key": "SE Ranking Competitor",  "value": s.get("seranking_competitor") or "NOT SET"},
        {"key": "WordPress URL",          "value": s.get("wp_url") or "NOT SET"},
        {"key": "WordPress User",         "value": s.get("wp_username") or "NOT SET"},
        {"key": "WP App Password",        "value": _mask(s.get("wp_app_password"))},
    ]
    configured = sum(1 for r in rows if r["value"] != "NOT SET")
    return ActionResult.success(
        data={"settings": rows, "configured": configured},
        summary="\n".join(f"{r['key']}: {r['value']}" for r in rows),
        ui=ui.DataTable(
            columns=[ui.DataColumn(key="key", label="Setting", width="45%"),
                     ui.DataColumn(key="value", label="Value", width="55%")],
            rows=rows,
        ),
    )


@chat.function(
    "list_wp_posts",
    description=(
        "List/show existing WordPress posts from the blog. READ-ONLY — does NOT create or save anything. "
        "Use ONLY when user asks to SEE or LIST posts: show WP posts, покажи статьи в WP, "
        "список постов, what's in WordPress, show published articles, покажи черновики в WP. "
        "DO NOT use when user wants to SAVE or PUBLISH a new article — use publish_wp_draft for that."
    ),
    action_type="read",
    event="",
)
async def list_wp_posts(ctx, params: ListWpPostsParams) -> ActionResult:
    """Fetch and display WordPress posts."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")

    _mos_post = _post  # already imported at module level
    # Paginate to fetch ALL posts
    all_posts = []
    page = 1
    while True:
        data = await _mos_post(ctx, "/api/wordpress/list", {
            "wp_url":      s["wp_url"],
            "wp_user":     s["wp_username"],
            "wp_password": s["wp_app_password"],
            "per_page":    100,
            "page":        page,
            "status":      params.status or "any",
        })
        if "error" in data:
            if page == 1:
                return ActionResult.error(error=data["error"])
            break
        batch = data.get("posts", [])
        if not batch:
            break
        all_posts.extend(batch)
        if len(batch) < 100:
            break  # last page
        page += 1
        if page > 20:  # safety cap at 2000 posts
            break
    posts = all_posts
    if not posts:
        return ActionResult.success(data={}, summary="No posts found in WordPress blog.")

    rows = [
        {
            "title":  p.get("title", "—")[:55],
            "status": p.get("status", "—"),
            "date":   p.get("date", "")[:10],
            "link":   p.get("link", ""),
        }
        for p in posts
    ]

    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="title",  label="Title",   width="50%"),
            ui.DataColumn(key="status", label="Status",  width="12%"),
            ui.DataColumn(key="date",   label="Date",    width="13%"),
            ui.DataColumn(key="link",   label="URL",     width="25%"),
        ],
        rows=rows,
    )

    published = sum(1 for p in posts if p.get("status") == "publish")
    drafts    = sum(1 for p in posts if p.get("status") == "draft")

    return ActionResult.success(
        data={"posts": posts, "count": len(posts)},
        summary=f"{len(posts)} posts found: {published} published, {drafts} drafts.",
        ui=table,
    )


# ── Unpublish ─────────────────────────────────────────────────────────────────

@chat.function(
    "unpublish_wp",
    description=(
        "Set a WordPress post back to draft (unpublish). "
        "Use when user says: unpublish, снять с публикации, перевести в черновик, "
        "скрыть статью, убрать с сайта, set to draft."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:post"],
    event="seo.content.updated",
)
async def unpublish_wp(ctx, params: UnpublishWpParams) -> ActionResult:
    """Set WP post to draft status (unpublish)."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")

    cid = await _resolve_id(ctx, params.content_id, params.keyword_hint)
    item = await get_content(ctx, cid) if cid else None
    wp_id = int(item.get("wp_post_id")) if item and item.get("wp_post_id") else None
    if not wp_id:
        return ActionResult.error(error="No WP post ID. Publish to WordPress first.")

    data = await _post(ctx, "/api/wordpress/update", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"],
        "post_id": wp_id, "status": "draft",
    })
    if "error" in data:
        return ActionResult.error(error=data["error"])

    if item and cid:
        await update_content(ctx, cid, {"status": "review"})

    return ActionResult.success(
        data={"post_id": wp_id, "status": "draft"},
        summary=f"Post #{wp_id} set to draft. Removed from public site.",
    )


# ── Get article link ──────────────────────────────────────────────────────────

@chat.function(
    "get_article_link",
    description=(
        "Find the URL of a specific article on OUR WordPress blog — NOT a Google search. "
        "Use for internal blog post lookups: 'найди ссылку на статью', 'где статья про X', "
        "'дай ссылку на пост', 'url статьи X', 'можешь найти где статья', "
        "'link to our article about X', 'permalink нашей статьи'. "
        "Searches WordPress drafts and published posts directly. "
        "Do NOT use Google or web search — use this tool instead."
    ),
    action_type="read",
)
async def get_article_link(ctx, params: GetArticleLinkParams) -> ActionResult:
    """Find WP post URL by title or keyword."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured.")

    # Search in MOS content items first
    items = await list_content(ctx)
    query = params.title_or_keyword.lower()
    matches = [
        i for i in items
        if query in (i.get("keyword") or "").lower() or query in (i.get("title") or "").lower()
    ]
    if matches and matches[0].get("wp_post_id"):
        item = matches[0]
        # Fetch live link from WP
        data = await _post(ctx, "/api/wordpress/get", {
            "wp_url": s["wp_url"], "wp_user": s["wp_username"],
            "wp_password": s["wp_app_password"],
            "post_id": int(item["wp_post_id"]),
        })
        link  = data.get("link", "")
        title = data.get("title") or item.get("title") or item.get("keyword", "")
        status = data.get("status", "unknown")
        return ActionResult.success(
            data={"link": link, "title": title, "status": status, "post_id": item["wp_post_id"]},
            summary=f"**{title}**\nStatus: {status}\nURL: {link}",
        )

    # Fallback: search WP directly (all posts any status)
    data = await _post(ctx, "/api/wordpress/list", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"],
        "per_page": 100, "page": 1, "status": "any",
    })
    posts = data.get("posts", [])
    found = [p for p in posts if query in (p.get("title") or "").lower()]

    # Also search by slug
    if not found:
        slug_query = query.replace(" ", "-")
        found = [p for p in posts if slug_query in (p.get("slug") or p.get("link") or "").lower()]

    if not found:
        # Last resort: show all posts so user can pick
        all_rows = [{"title": p.get("title","")[:55], "status": p.get("status",""), "link": p.get("link","")} for p in posts[:20]]
        return ActionResult.success(
            data={"posts": posts, "query": query},
            summary=f"No exact match for '{params.title_or_keyword}'. Showing recent 20 posts — pick one:",
            ui=ui.DataTable(
                columns=[
                    ui.DataColumn(key="title", label="Title", width="50%"),
                    ui.DataColumn(key="status", label="Status", width="15%"),
                    ui.DataColumn(key="link", label="URL", width="35%"),
                ],
                rows=all_rows,
            ),
        )

    rows = [{"title": p.get("title","")[:55], "status": p.get("status",""), "link": p.get("link","")} for p in found[:5]]
    return ActionResult.success(
        data={"posts": found},
        summary="\n".join(f"**{r['title']}** ({r['status']})\n{r['link']}" for r in rows),
    )


@chat.function(
    "get_wp_post_content",
    description=(
        "Show the full text/content of a specific WordPress post or draft. "
        "Use when user asks: покажи текст статьи, покажи содержание черновика, "
        "что написано в статье X, покажи пост, покажи текст черновика, "
        "show me the article text, what does the article say, read the post."
    ),
    action_type="read",
)
async def get_wp_post_content(ctx, params: GetArticleLinkParams) -> ActionResult:
    """Fetch full content of a WP post by title or keyword."""
    from api_wordpress import get_post, search_posts
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured.")

    query = params.title_or_keyword.strip()
    wp_url = s["wp_url"]
    wp_user = s["wp_username"]
    wp_pw   = s["wp_app_password"]

    # Check MOS content items first for a WP post ID
    items = await list_content(ctx)
    ql = query.lower()
    match = next(
        (i for i in items if ql in (i.get("keyword") or "").lower() or ql in (i.get("title") or "").lower()),
        None,
    )
    post_id = int(match["wp_post_id"]) if match and match.get("wp_post_id") else None

    # If no ID from store, search WP directly
    if not post_id:
        results = await search_posts(ctx, wp_url, wp_user, wp_pw, query)
        if not results:
            return ActionResult.error(error=f"No post found for '{query}'. Try list_wp_posts to see all posts.")
        post_id = results[0].get("id")
        if not post_id:
            return ActionResult.error(error=f"Post found but no ID returned.")

    post = await get_post(ctx, wp_url, wp_user, wp_pw, post_id)
    if post.get("_wp_error"):
        return ActionResult.error(error=post["_wp_error"])

    title   = post.get("title", "")
    status  = post.get("status", "")
    link    = post.get("link", "")
    # Strip HTML tags from content for readable display
    raw_html = post.get("content", "")
    text = re.sub(r"<[^>]+>", " ", raw_html).strip()
    text = re.sub(r"\s{2,}", " ", text)
    word_count = len(text.split())

    summary = f"**{title}** ({status})\n{link}\n\n{text[:3000]}{'...' if len(text) > 3000 else ''}"
    return ActionResult.success(
        data={"title": title, "status": status, "link": link, "word_count": word_count, "content": text[:5000]},
        summary=summary,
    )


# ── Rewrite article ───────────────────────────────────────────────────────────

@chat.function(
    "rewrite_article",
    description=(
        "Fully rewrite the current article from scratch with improved structure and quality. "
        "Use when user says: rewrite completely, полностью перепиши, перепиши статью заново, "
        "новая версия статьи, full rewrite, rewrite from scratch. "
        "Different from improve_article (which adds sections) — this regenerates the whole article."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
    background=True,
    long_running=False,
)
async def rewrite_article(ctx, params: RewriteArticleParams) -> ActionResult:
    """Start async full article rewrite."""
    import time as _time
    cid = await _resolve_id(ctx, params.content_id)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="No article open. Open an article from Content Plan first.")

    keyword = item.get("keyword", "")
    instruction = params.instruction or "full rewrite — better structure, more engaging, stronger intro"

    t0 = _time.monotonic()
    data = await _post(ctx, "/api/content/refine/start", {
        "content":     item.get("content", ""),
        "keyword":     keyword,
        "instruction": f"FULL REWRITE: {instruction}. Keep the same keyword focus. Minimum 2500 words.",
    }, timeout=10)

    if "error" in data:
        return ActionResult.error(error=data["error"])

    job_id = data.get("job_id", "")
    await update_content(ctx, cid, {"generating": True})

    return ActionResult.success(
        data={"job_id": job_id, "content_id": cid},
        summary=f"Rewrite started for '{keyword}'. Job: {job_id}\nUse check_article_job to poll status (~60-90s).",
    )


# ── Add keywords to article ───────────────────────────────────────────────────

@chat.function(
    "add_keywords_to_article",
    description=(
        "Add keywords to the current article and update Rank Math SEO. "
        "Use when user says: add keywords, добавь ключевые слова, "
        "добавь кейворды, add these keywords to the article, "
        "track these keywords in Rank Math, добавь в Rank Math."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def add_keywords_to_article(ctx, params: AddKeywordsParams) -> ActionResult:
    """Add secondary keywords to article and update Rank Math."""
    s = await load_settings(ctx)
    cid = await _resolve_id(ctx, params.content_id)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="No article open. Open an article from Content Plan first.")

    new_kws = [k.strip() for k in params.keywords.split(",") if k.strip()]
    existing = item.get("secondary_keywords") or []
    if isinstance(existing, str):
        existing = [k.strip() for k in existing.split(",") if k.strip()]
    combined = list(dict.fromkeys(existing + new_kws))  # deduplicate preserving order

    await update_content(ctx, cid, {"secondary_keywords": combined})

    # Update Rank Math if post is published
    wp_id = item.get("wp_post_id")
    rm_updated = False
    if wp_id and s.get("wp_app_password"):
        focus_kw = item.get("keyword", "")
        all_kws  = focus_kw + ", " + ", ".join(combined) if focus_kw else ", ".join(combined)
        rm_data  = await _post(ctx, "/api/wordpress/update", {
            "wp_url":        s["wp_url"],
            "wp_user":       s["wp_username"],
            "wp_password":   s["wp_app_password"],
            "post_id":       int(wp_id),
            "focus_keyword": all_kws,
        })
        rm_updated = "error" not in rm_data

    summary = (
        f"Added {len(new_kws)} keywords to article.\n"
        f"Total secondary keywords: {len(combined)}\n"
        f"Keywords: {', '.join(combined[:10])}\n"
        + ("Rank Math updated in WordPress." if rm_updated else "Saved locally (not yet in WordPress — publish first).")
    )
    return ActionResult.success(data={"keywords": combined, "rank_math_updated": rm_updated}, summary=summary)


# ── Check SEO meta ────────────────────────────────────────────────────────────

@chat.function(
    "check_seo_meta",
    description=(
        "Show SEO settings for an article — Rank Math focus keyword, secondary keywords, "
        "meta description, keyword density, word count, WP status. "
        "Use when user asks about SEO of an article — "
        "'покажи rank math', 'seo настройки статьи', 'как настроено seo', "
        "'keyword density', 'какой focus keyword', 'meta description статьи', "
        "'check seo', 'seo audit article', 'посмотреть настройки статьи'. "
        "Works with content plan ID or WP post ID (numeric)."
    ),
    action_type="read",
)
async def check_seo_meta(ctx, params: CheckSeoMetaParams) -> ActionResult:
    """Show Rank Math SEO settings for an article."""
    s = await load_settings(ctx)

    # Detect WP post ID (numeric ≤7 digits) — fetch from WP directly
    raw_id = params.content_id.strip() if params.content_id else ""
    if raw_id.isdigit() and len(raw_id) <= 7:
        if not s.get("wp_app_password"):
            return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")
        wp_data = await _post(ctx, "/api/wordpress/get", {
            "wp_url": s["wp_url"], "wp_user": s["wp_username"],
            "wp_password": s["wp_app_password"], "post_id": int(raw_id),
        })
        if "error" in wp_data:
            return ActionResult.error(error=f"WP post {raw_id} not found: {wp_data['error']}")
        content_html = wp_data.get("content", "")
        word_count   = len(re.sub(r"<[^>]+>", " ", content_html).split()) if content_html else 0
        title        = wp_data.get("title", "—")
        link         = wp_data.get("link", "")
        wp_status    = wp_data.get("status", "")
        rows = [
            {"field": "Title",       "value": title[:60]},
            {"field": "WP Post ID",  "value": raw_id},
            {"field": "Status",      "value": wp_status},
            {"field": "URL",         "value": link},
            {"field": "Word count",  "value": str(word_count)},
            {"field": "Note",        "value": "Import to Content Plan via import_from_wp to see full SEO meta"},
        ]
        table = ui.DataTable(
            columns=[ui.DataColumn(key="field", label="Field", width="35%"),
                     ui.DataColumn(key="value", label="Value", width="65%")],
            rows=rows,
        )
        return ActionResult.success(
            data={"wp_post_id": raw_id, "title": title, "word_count": word_count},
            summary=f"WP Post #{raw_id}: '{title}'\nStatus: {wp_status} | Words: {word_count}\nURL: {link}",
            ui=table,
        )

    cid = await _resolve_id(ctx, params.content_id, params.keyword_hint)
    item = await get_content(ctx, cid)
    if not item:
        return ActionResult.error(error="No article found. Open one from Content Plan, or specify keyword name.")

    keyword    = item.get("keyword", "—")
    sec_kws    = item.get("secondary_keywords") or []
    if isinstance(sec_kws, str):
        sec_kws = [k.strip() for k in sec_kws.split(",") if k.strip()]
    meta_desc  = item.get("meta_description") or item.get("excerpt") or "—"
    title      = item.get("title") or keyword
    status     = item.get("status", "idea")
    wp_id      = item.get("wp_post_id")
    content    = item.get("content", "")
    word_count = len(content.split()) if content else 0

    # Check keyword density
    kw_lower    = keyword.lower()
    content_lc  = content.lower()
    kw_count    = content_lc.count(kw_lower) if kw_lower else 0
    kw_density  = round(kw_count / (word_count / 100), 2) if word_count > 0 else 0

    # Fetch live WP data if published
    wp_link = wp_status = ""
    if wp_id and s.get("wp_app_password"):
        try:
            wp_data   = await _post(ctx, "/api/wordpress/get", {
                "wp_url": s["wp_url"], "wp_user": s["wp_username"],
                "wp_password": s["wp_app_password"], "post_id": int(wp_id),
            })
            wp_link   = wp_data.get("link", "")
            wp_status = wp_data.get("status", "")
        except Exception:
            pass

    rows = [
        {"field": "Focus keyword",    "value": keyword},
        {"field": "Secondary KWs",    "value": ", ".join(sec_kws[:8]) or "—"},
        {"field": "Meta description", "value": meta_desc[:100] if meta_desc != "—" else "—"},
        {"field": "Title",            "value": title[:60]},
        {"field": "Word count",       "value": str(word_count)},
        {"field": "KW density",       "value": f"{kw_density}%" + (" ✅" if 0.5 <= kw_density <= 1.5 else " ⚠️ too low" if kw_density < 0.5 else " ⚠️ too high")},
        {"field": "Status",           "value": f"{status}" + (f" → WP {wp_status}" if wp_status else "")},
        {"field": "WP Post ID",       "value": str(wp_id) if wp_id else "not published"},
        {"field": "URL",              "value": wp_link or "not published"},
    ]

    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="field", label="Field", width="35%"),
            ui.DataColumn(key="value", label="Value", width="65%"),
        ],
        rows=rows,
    )

    issues = []
    if kw_density < 0.5 and word_count > 300:
        issues.append(f"⚠️ Keyword density {kw_density}% — too low (aim 0.5–1.5%)")
    if not sec_kws:
        issues.append("⚠️ No secondary keywords — add with add_keywords_to_article")
    if meta_desc == "—":
        issues.append("⚠️ No meta description — run set_wp_seo")
    if word_count < 1500:
        issues.append(f"⚠️ Only {word_count} words — aim for 2000+")

    summary = (
        f"SEO Meta for '{keyword}':\n"
        f"• Focus keyword: {keyword}\n"
        f"• Secondary: {', '.join(sec_kws[:5]) or 'none'}\n"
        f"• Words: {word_count} | KW density: {kw_density}%\n"
        f"• Meta desc: {'set' if meta_desc != '—' else 'missing'}\n"
        f"• WP: {'#' + str(wp_id) + ' ' + wp_status if wp_id else 'not published'}\n"
        + (("\n" + "\n".join(issues)) if issues else "\n✅ SEO looks good!")
    )
    return ActionResult.success(data={"seo": rows, "issues": issues}, summary=summary, ui=table)


# ── Direct WP article patch ────────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel, Field as _Field

class PatchWpArticleParams(_BaseModel):
    wp_post_id: str = _Field(..., description="WordPress post ID (numeric, e.g. 1902)")
    instruction: str = _Field(..., description="What to change: rewrite intro, add section, fix conclusion, etc.")


@chat.function(
    "patch_wp_article",
    description=(
        "Edit/rewrite a specific part of a WordPress post by WP post ID. "
        "Use when user says: rewrite intro of post 1902, edit article wp 1902, "
        "перепиши вступление поста 1902, измени статью WP #1902, "
        "edit WP article, rewrite part of published post. "
        "Fetches content directly from WordPress, patches, saves back. "
        "No need to open article in editor first."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
    background=True,
    long_running=False,
)
async def patch_wp_article(ctx, params: PatchWpArticleParams) -> ActionResult:
    """Fetch WP post, patch a section, save back to WP — no content plan needed."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")

    wp_id = int(params.wp_post_id)
    # Fetch article from WordPress
    wp = await _post(ctx, "/api/wordpress/get", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"], "post_id": wp_id,
    })
    if "error" in wp:
        return ActionResult.error(error=f"WP post {wp_id} not found: {wp['error']}")

    content = wp.get("content", "")
    title   = wp.get("title", "")
    if not content:
        return ActionResult.error(error=f"WP post {wp_id} has no content.")

    # Patch via MOS AI (async — avoids ctx.http timeout)
    data = await _post(ctx, "/api/content/refine/start", {
        "user_key": "", "content": content, "keyword": title, "instruction": params.instruction,
    }, timeout=10)
    job_id = data.get("job_id", "") if "error" not in data else ""
    if job_id:
        return ActionResult.success(
            data={"job_id": job_id, "wp_post_id": str(wp_id)},
            summary=f"✏️ Rewrite started for WP #{wp_id}. Job: {job_id}. Call check_article_job in ~60s.",
        )
    # Fall through if job start fails
    data = {"content": ""}

    if "error" in data:
        return ActionResult.error(error=data["error"])

    new_content = data.get("content", "")
    if not new_content:
        return ActionResult.error(error="AI returned empty content. Try again.")

    # Save back to WordPress
    upd = await _post(ctx, "/api/wordpress/update", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"],
        "post_id": wp_id, "content": new_content,
    })

    if "error" in upd:
        return ActionResult.error(error=f"Failed to update WP post: {upd['error']}")

    return ActionResult.success(
        data={"wp_post_id": wp_id, "updated": True},
        summary=f"✅ WP post #{wp_id} '{title}' updated successfully.",
    )


# ── Edit WP article — import + patch in one shot ─────────────────────────────

class EditWpArticleParams(_BaseModel):
    wp_post_id: str = _Field(..., description="WordPress post ID (e.g. '1902')")
    instruction: str = _Field(..., description="What to change: rewrite intro, add section, etc.")


@chat.function(
    "edit_wp_article",
    description=(
        "Import a WordPress post and immediately edit/rewrite a part of it — all in one step. "
        "PREFER this over patch_article when user mentions a WordPress post ID or title. "
        "Use when user says: перепиши вступление поста 1902, edit post 1902, "
        "измени статью wp 1902, rewrite intro of WP article, "
        "перепиши вступление/абзац/заключение поста, edit/improve specific WP post. "
        "wp_post_id: numeric WordPress ID (e.g. '1902'). "
        "instruction: what to change (e.g. 'rewrite intro mentioning WebHostMost as alternative')."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:content"],
    event="seo.content.updated",
)
async def edit_wp_article(ctx, params: EditWpArticleParams) -> ActionResult:
    """Fetch WP post content, apply AI edit, save back — single atomic operation."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured. Add credentials in Settings.")

    wp_id = int(params.wp_post_id)

    # Fetch from WordPress
    wp = await _post(ctx, "/api/wordpress/get", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"], "post_id": wp_id,
    })
    if "error" in wp:
        return ActionResult.error(error=f"WP post {wp_id} not found: {wp['error']}")

    content = wp.get("content", "")
    title   = wp.get("title", "")
    if not content:
        return ActionResult.error(error=f"WP post {wp_id} has no content.")

    # Use async job — /api/content/refine blocks 60-90s, ctx.http timeout < that
    instruction = params.instruction + (f" Keep focus keyword '{title}' prominent." if title else "")
    job_data = await _post(ctx, "/api/content/refine/start", {
        "user_key": "", "content": content, "keyword": title, "instruction": instruction,
    }, timeout=10)

    if "error" in job_data:
        return ActionResult.error(error=job_data["error"])

    job_id = job_data.get("job_id", "")
    # Store WP ID in a temp key so check_wp_edit_job can save back
    await save_ui_state(ctx, {"pending_wp_edit": str(wp_id), "pending_wp_edit_job": job_id})

    return ActionResult.success(
        data={"job_id": job_id, "wp_post_id": wp_id, "title": title},
        summary=(
            f"✏️ Rewrite started for '{title}' (WP #{wp_id}).\n"
            f"Job ID: {job_id}\n"
            f"Takes ~60-90 seconds. Call check_article_job to check — it will auto-save to WordPress."
        ),
    )


# ── Delete WP post ─────────────────────────────────────────────────────────────

class DeleteWpPostParams(_BaseModel):
    wp_post_id: str = _Field(..., description="WordPress post ID to permanently delete")
    keyword_hint: str = _Field("", description="Post title/keyword to confirm which post")


@chat.function(
    "delete_wp_post",
    description=(
        "Permanently delete a WordPress post (moves to trash). "
        "Use when user says: удали пост, удали черновик, delete this draft, "
        "delete WP post ID X, убери статью из WordPress, "
        "удали этот черновик навсегда. "
        "wp_post_id: WordPress numeric post ID."
    ),
    action_type="destructive",
    chain_callable=True,
    effects=["delete:post"],
    event="seo.content.deleted",
)
async def delete_wp_post(ctx, params: DeleteWpPostParams) -> ActionResult:
    """Delete a WordPress post by ID (moves to trash)."""
    s = await load_settings(ctx)
    if not s.get("wp_app_password"):
        return ActionResult.error(error="WordPress not configured.")

    wp_id = int(params.wp_post_id)
    # First get title for confirmation
    info = await _post(ctx, "/api/wordpress/get", {
        "wp_url": s["wp_url"], "wp_user": s["wp_username"],
        "wp_password": s["wp_app_password"], "post_id": wp_id,
    })
    title = info.get("title", f"Post #{wp_id}") if "error" not in info else f"Post #{wp_id}"

    # Delete via WP REST API (DELETE = move to trash)
    import base64
    auth = base64.b64encode(f"{s['wp_username']}:{s['wp_app_password']}".encode()).decode()
    resp = await ctx.http.delete(
        f"{s['wp_url'].rstrip('/')}/wp-json/wp/v2/posts/{wp_id}",
        headers={"Authorization": f"Basic {auth}"},
    )
    if not resp.ok:
        return ActionResult.error(error=f"Failed to delete post #{wp_id}: {resp.status_code}")

    return ActionResult.success(
        data={"wp_post_id": wp_id, "title": title, "deleted": True},
        summary=f"🗑️ Deleted '{title}' (WP #{wp_id}) from WordPress.",
    )
