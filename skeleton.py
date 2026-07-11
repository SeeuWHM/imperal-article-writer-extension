"""Skeleton context providers — inject background facts into Webbee LLM context.

Per Valya/SDK: skeleton = LLM context cache holding ready API responses.
More data in skeleton = better Webbee routing and answers.
"""
from wpb_app import ext, load_ui_state, get_content, load_settings, list_content, ser_ready, wp_ready, gsc_ready


@ext.skeleton("current_article", ttl=30,
              description="Currently open article in editor — keyword, title, word count, status, article_id")
async def skeleton_refresh_current_article(ctx) -> dict:
    """Slow-changing background fact: which article is in the editor."""
    state = await load_ui_state(ctx)
    selected_id = state.get("selected_id")

    if not selected_id:
        return {"response": {
            "has_open_article": False,
            "article_id": "",
            "keyword": "",
            "word_count": 0,
            "instruction": "No article is open in the editor.",
        }}

    item = await get_content(ctx, selected_id)
    if not item:
        return {"response": {
            "has_open_article": False,
            "article_id": selected_id,
            "instruction": "Article ID set but not found — may have been deleted.",
        }}

    content = item.get("content", "")
    word_count = len(content.split()) if content else 0
    kw = item.get("keyword") or item.get("title", "untitled")

    return {"response": {
        "has_open_article": True,
        "article_id": selected_id,
        "keyword": kw,
        "title": item.get("title", ""),
        "status": item.get("status", "idea"),
        "word_count": word_count,
        "wp_post_id": str(item.get("wp_post_id") or ""),
        "has_content": word_count > 50,
        "instruction": (
            f"OPEN ARTICLE: '{kw}' | {word_count} words | status={item.get('status','idea')} | "
            f"article_id={selected_id} | wp_post_id={item.get('wp_post_id','')}. "
            f"Use article_id={selected_id} with patch_article/improve_article/check_article_quality."
        ),
    }}


@ext.skeleton("content_overview", ttl=120,
              description="Content plan totals: ideas, writing, review, published counts")
async def skeleton_refresh_content_overview(ctx) -> dict:
    """Background snapshot of content plan state."""
    try:
        items = await list_content(ctx)
    except Exception:
        items = []

    counts = {"idea": 0, "writing": 0, "review": 0, "published": 0}
    in_wp = 0
    for i in items:
        s = i.get("status", "idea")
        counts[s] = counts.get(s, 0) + 1
        if i.get("wp_post_id"):
            in_wp += 1

    return {"response": {
        "total": len(items),
        "ideas": counts["idea"],
        "writing": counts["writing"],
        "review": counts["review"],
        "published": counts["published"],
        "in_wordpress": in_wp,
        "instruction": (
            f"Content plan: {len(items)} total — "
            f"{counts['idea']} ideas, {counts['writing']} writing, "
            f"{counts['review']} in review, {counts['published']} published, "
            f"{in_wp} synced to WordPress."
        ),
    }}


@ext.skeleton("wp_config", ttl=600,
              description="WordPress, SE Ranking, GSC, and Matomo Analytics connection status, site domain, brand info")
async def skeleton_refresh_wp_config(ctx) -> dict:
    s = await load_settings(ctx)
    wp_ok   = wp_ready(s)
    ser_ok  = ser_ready(s)
    gsc_ok  = gsc_ready(s)
    proj_ok = bool(s.get("seranking_project_id"))

    # Check Matomo Analytics availability via cross-extension IPC
    matomo_ok = False
    matomo_url = ""
    try:
        mc = await ctx.extensions.call("analytics", "matomo_config")
        if mc and not getattr(mc, "error", None):
            d = getattr(mc, "data", {}) or {}
            matomo_ok  = bool(d.get("configured"))
            matomo_url = d.get("matomo_url", "")
    except Exception:
        pass

    return {"response": {
        "wordpress_connected": wp_ok,
        "seranking_data_connected": ser_ok,
        "seranking_project_connected": proj_ok,
        "gsc_connected": gsc_ok,
        "matomo_connected": matomo_ok,
        "matomo_url": matomo_url,
        "wp_url": s.get("wp_url", ""),
        "blog_url": s.get("blog_url", ""),
        "gsc_site_url": s.get("gsc_site_url", ""),
        "blog_domain": s.get("seranking_domain", ""),
        "company_name": s.get("company_name", ""),
        "brand_voice": s.get("brand_voice", ""),
        "instruction": (
            f"WordPress: {'✓' if wp_ok else '✗ NOT connected'}. "
            f"SE Ranking: {'✓ research+tracking' if (ser_ok and proj_ok) else '✓ research only' if ser_ok else '✗'}. "
            f"GSC: {'✓' if gsc_ok else '✗'}. "
            f"Matomo Analytics (via Analytics extension IPC): {'✓ connected at ' + matomo_url if matomo_ok else '✗ NOT connected — user must install Analytics extension'}. "
            f"Domain: {s.get('seranking_domain','not set')}. "
            f"Brand: {s.get('company_name','not set')}."
        ),
    }}


@ext.skeleton("content_list", ttl=60,
              description="All content items: id, keyword, title, status, word_count, wp_post_id — full list for article management")
async def skeleton_refresh_content_list(ctx) -> dict:
    try:
        items = await list_content(ctx)
    except Exception:
        items = []

    summaries = []
    by_status = {}
    for i in items:
        content = i.get("content", "")
        wc = len(content.split()) if content else 0
        status = i.get("status", "idea")
        by_status[status] = by_status.get(status, 0) + 1
        summaries.append({
            "id": i.get("id", ""),
            "keyword": i.get("keyword", ""),
            "title": i.get("title", ""),
            "status": status,
            "word_count": wc,
            "wp_post_id": str(i.get("wp_post_id") or ""),
        })

    instruction = (
        f"{len(summaries)} articles total: "
        + ", ".join(f"{v} {k}" for k, v in by_status.items())
        + ". Use id= to reference specific articles with open_editor/ai_write/patch_wp_article."
    )

    return {"response": {
        "items": summaries,
        "total": len(summaries),
        "by_status": by_status,
        "instruction": instruction,
    }}
