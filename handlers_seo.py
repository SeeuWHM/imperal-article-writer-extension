"""SE Ranking handlers — keywords, gaps, rankings, content plan."""
import asyncio
import traceback

from imperal_sdk import ActionResult, ui
from imperal_sdk.types import ActionResult  # noqa: F811

from wpb_app import chat, load_settings, save_settings, save_ui_state, create_content, list_content, gsc_ready
from api_client import (ser_keywords, ser_gaps, ser_rankings, ser_projects, content_plan, fetch_ai_traffic, _post,
                        gsc_verify, gsc_pages, gsc_top_queries, gsc_anomalies, gsc_growth_opportunities, _gsc_auth_payload)
from handlers_docs import _load_docs
from params import FetchKeywordsParams, FetchGapsParams, FetchRankingsParams, ListProjectsParams, BuildPlanParams, SetupBlogStyleParams
from response_models import KeywordResultsResponse, GapResultsResponse, RankingsResponse, ProjectsResponse, GenericPayloadResponse


@chat.function(
    "fetch_keywords",
    description=(
        "Find keywords using SE Ranking — keyword research, volume, difficulty, positions. "
        "Use when user asks: find keywords, what keywords to target, keyword ideas for topic X, "
        "show me keywords for [topic], поиск ключевых слов, найди ключевые слова, "
        "какие ключевики взять, keywords for [topic/niche]. "
        "Uses configured domain by default. All params optional."
    ),
    action_type="read",
    event="seo.nav.changed",
    data_model=KeywordResultsResponse,
)
async def fetch_keywords(ctx, params: FetchKeywordsParams) -> ActionResult:
    """Fetch organic keywords for the domain from SE Ranking."""
    s = await load_settings(ctx)
    domain = params.domain or s.get("seranking_domain", "")
    source = params.source or s.get("seranking_source", "us")
    if not domain:
        return ActionResult.error(error="Domain not configured. Go to Settings → SE Ranking.")

    data = await ser_keywords(ctx, domain, source, params.limit, params.min_volume, params.max_difficulty)
    if "error" in data:
        return ActionResult.error(error=data["error"])

    kws = data.get("keywords", [])
    await save_ui_state(ctx, {"active_view": "keywords", "kw_results": kws[:100]})

    top = kws[:5]
    lines = [f"- {k.get('keyword')} pos:{k.get('position')} vol:{k.get('volume')} diff:{k.get('difficulty')}" for k in top]
    return ActionResult.success(
        data={"count": len(kws), "keywords": kws},
        summary=f"Found {len(kws)} keywords for {domain}:\n" + "\n".join(lines),
    )


@chat.function(
    "fetch_gaps",
    description=(
        "Find keyword gaps vs competitor — keywords competitor ranks for but we don't. "
        "Use when user asks: what keywords am I missing, gap analysis, competitor keywords, "
        "что я упускаю по ключевым словам, анализ конкурентов, keyword gaps."
    ),
    action_type="read",
    event="seo.nav.changed",
    data_model=GapResultsResponse,
)
async def fetch_gaps(ctx, params: FetchGapsParams) -> ActionResult:
    """Fetch keyword gaps vs a competitor domain."""
    s = await load_settings(ctx)
    if not s.get("seranking_api_key"):
        return ActionResult.error(error="SE Ranking API key not configured. Go to Settings.")
    domain = s.get("seranking_domain", "")
    source = params.source or s.get("seranking_source", "us")
    if not domain:
        return ActionResult.error(error="Domain not configured. Go to Settings → SE Ranking.")

    data = await ser_gaps(ctx, domain, params.competitor, source, params.limit)
    if "error" in data:
        return ActionResult.error(error=data["error"])

    gaps = data.get("keywords", [])
    await save_ui_state(ctx, {"active_view": "keywords", "kw_results": gaps[:100]})

    top = gaps[:5]
    lines = [f"- {k.get('keyword')} vol:{k.get('volume')} diff:{k.get('difficulty')}" for k in top]
    return ActionResult.success(
        data={"count": len(gaps), "keywords": gaps, "competitor": params.competitor},
        summary=f"Found {len(gaps)} gap keywords vs {params.competitor}:\n" + "\n".join(lines),
    )


@chat.function(
    "fetch_rankings",
    description=(
        "Show ORGANIC Google search positions from SE Ranking — NOT Microsoft Ads, NOT paid advertising. "
        "Use for SEO keyword ranking positions only. "
        "покажи мои позиции, позиции в Google, SEO позиции, "
        "мои позиции в поиске, покажи SEO Rankings, "
        "на каком месте сайт в Google, keyword rankings, органические позиции."
    ),
    action_type="read",
    event="seo.nav.changed",
    data_model=RankingsResponse,
)
async def fetch_rankings(ctx, params: FetchRankingsParams) -> ActionResult:
    """Fetch keyword rankings + AI referrer traffic in parallel."""
    rankings_data, ai_data = await asyncio.gather(
        ser_rankings(ctx),
        fetch_ai_traffic(ctx),
    )
    if "error" in rankings_data:
        return ActionResult.error(error=rankings_data["error"])

    rankings = rankings_data.get("rankings", [])
    await save_ui_state(ctx, {
        "active_view": "rankings",
        "rankings_results": rankings[:200],
        "ai_traffic": ai_data,
    })

    ranked = [r for r in rankings if r.get("position", 0) > 0]
    top3   = sum(1 for r in ranked if r.get("position", 0) <= 3)
    top10  = sum(1 for r in ranked if r.get("position", 0) <= 10)
    top_kws = sorted(ranked, key=lambda r: r.get("position", 999))[:3]
    lines  = [f"#{r['position']} {r['keyword']}" for r in top_kws]

    ai_sources = ai_data.get("sources", [])
    ai_total   = ai_data.get("total_visits", 0)
    ai_change  = ai_data.get("total_change_pct", 0)
    ai_line    = f"AI traffic: {ai_total} visits ({'+' if ai_change >= 0 else ''}{ai_change}% vs last month)" if ai_total else ""

    summary = (
        f"Loaded {len(rankings)} tracked keywords: {len(ranked)} ranked, {top3} top-3, {top10} top-10.\n"
        f"Top positions: {', '.join(lines)}\n"
        + (ai_line or "No AI referrer traffic detected this month (ChatGPT, Perplexity, Gemini).")
    )
    return ActionResult.success(
        data={"count": len(rankings), "rankings": rankings, "ai_traffic": ai_data},
        summary=summary,
    )


@chat.function(
    "list_ser_projects",
    description="List SE Ranking projects — use this to find the project_id for settings.",
    action_type="read",
    data_model=ProjectsResponse,
)
async def list_ser_projects(ctx, params: ListProjectsParams) -> ActionResult:
    """List all SE Ranking projects to find the project ID."""
    data = await ser_projects(ctx)
    if "error" in data:
        return ActionResult.error(error=data["error"])

    projects = data.get("projects", [])
    lines = [f"- {p.get('id')} — {p.get('name', p.get('site', '?'))}" for p in projects[:20]]
    return ActionResult.success(
        data={"projects": projects},
        summary="SE Ranking projects:\n" + "\n".join(lines),
    )


@chat.function(
    "build_content_plan",
    description=(
        "Generate a 5-article content plan using SE Ranking keyword data and AI. "
        "Automatically avoids topics already published on the blog. "
        "Creates content items in the plan ready for writing."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:content"],
    event="seo.content.created",
)
async def build_content_plan(ctx, params: BuildPlanParams) -> ActionResult:
    """AI-generate a 5-article content plan. SE Ranking and GSC are optional enrichments."""
    s = await load_settings(ctx)
    # SE Ranking is optional — if not configured, AI uses blog URL + GSC data + topic context
    has_ser = bool(s.get("seranking_api_key") and s.get("seranking_domain"))

    language = params.language or "en"
    competitor = params.competitor or s.get("seranking_competitor", "")

    # Fetch GSC growth opportunities to inform content plan
    gsc_context = ""
    if gsc_ready(s):
        try:
            opps_data, queries_data = await asyncio.gather(
                gsc_growth_opportunities(ctx),
                gsc_top_queries(ctx),
                return_exceptions=True,
            )
            opps = opps_data.get("opportunities", [])[:10] if not isinstance(opps_data, Exception) else []
            queries = queries_data.get("queries", [])[:20] if not isinstance(queries_data, Exception) else []
            if opps:
                gsc_context += "\nGSC GROWTH OPPORTUNITIES (pages with high impressions, low CTR — optimize or expand):\n"
                for o in opps:
                    gsc_context += f"- {o['url']} | impr:{o['impressions']} | pos:{o['position']:.0f} | ctr:{o['ctr']:.1f}%\n"
            if queries:
                gsc_context += "\nGSC TOP QUERIES (real search terms bringing traffic — use for new article angles):\n"
                for q in queries[:15]:
                    gsc_context += f"- '{q['query']}' | clicks:{q['clicks']} | pos:{q['position']:.1f}\n"
        except Exception:
            pass

    existing_items = await list_content(ctx)
    # Only hard-block written/published content — ideas don't block new suggestions
    HARD_BLOCK_STATUSES = {"writing", "review", "published"}
    existing_kws = [
        i.get("keyword") or i.get("title") or ""
        for i in existing_items
        if (i.get("keyword") or i.get("title")) and i.get("status", "idea") in HARD_BLOCK_STATUSES
    ]

    data = await content_plan(ctx, competitor=competitor, language=language, existing_keywords=existing_kws)
    if "error" in data or not data.get("articles"):
        # Retry without filters
        data = await content_plan(ctx, competitor=competitor, language=language, existing_keywords=[])

    articles = data.get("articles", [])
    if not articles:
        return ActionResult.error(
            error="Could not generate content plan. "
                  + ("Connect SE Ranking in Settings for better results." if not has_ser else "Try again.")
        )

    # Dedup: skip if keyword already exists in MOS storage
    existing_all = await list_content(ctx)
    existing_kw_set = {(i.get("keyword") or "").lower() for i in existing_all if i.get("keyword")}

    created = 0
    for a in articles:
        kw = (a.get("keyword") or "").lower()
        if kw and kw in existing_kw_set:
            continue  # already in plan
        await create_content(ctx, {
            "keyword":    a.get("keyword", ""),
            "type":       a.get("article_type", "blog"),
            "title":      a.get("title", ""),
            "content":    "",
            "subject":    "",
            "status":     "idea",
            "volume":     a.get("volume", 0),
            "difficulty": a.get("difficulty", 0),
            "intent":     a.get("intent", ""),
            "priority":   a.get("priority", ""),
            "angle":               a.get("angle", ""),
            "writing_brief":       a.get("writing_brief", ""),
            "content_outline":     a.get("content_outline", []),
            "ai_visibility_hook":  a.get("ai_visibility_hook", ""),
            "target_reader":       a.get("target_reader", ""),
            "competitor_weakness": a.get("competitor_weakness", ""),
            "growth_reason":       a.get("growth_reason", ""),
            "secondary_keywords":  a.get("secondary_keywords", []),
            "wp_post_id": None,
            "ml_campaign_id": None,
        })
        created += 1

    kw_used = data.get("keywords_used", 0)
    gaps_used = data.get("gaps_used", 0)
    return ActionResult.success(
        data={"created": created, "keywords_used": kw_used, "gaps_used": gaps_used},
        summary=(
            f"Content plan ready: {created} articles added to the plan.\n"
            f"Based on {kw_used} keywords{f' + {gaps_used} gap keywords' if gaps_used else ''}.\n"
            "Open Content Plan to see them."
        ),
    )


@chat.function(
    "setup_blog_style",
    description=(
        "Analyze a blog URL and create a writing style profile for that blog. "
        "Use when user provides their blog URL and wants articles written in their style. "
        "Crawls RSS feed, analyzes recent posts, generates writing instructions."
    ),
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="seo.settings.saved",
)
async def setup_blog_style(ctx, params: SetupBlogStyleParams) -> ActionResult:
    """Analyze blog writing style and save as active brand profile."""
    s = await load_settings(ctx)
    blog_url = params.blog_url or s.get("blog_url", "")
    if not blog_url:
        return ActionResult.error(error="Provide your blog URL. Example: setup_blog_style with blog_url=https://blog.yourdomain.com")

    data = await _post(ctx, "/api/content/analyze_blog_style", {
        "blog_url":          blog_url,
        "language":          s.get("language", "en"),
        "posts_to_analyze":  5,
    }, timeout=90)

    if "error" in data:
        return ActionResult.error(error=data["error"])

    profile_text = data.get("profile", "")
    posts_count  = data.get("posts_analyzed", 0)

    # Save as MOS brand profile named "blog_style"
    save_result = await _post(ctx, "/api/profiles/save", {
        "name":    "blog_style",
        "content": profile_text,
    })
    if "error" not in save_result:
        await save_settings(ctx, {"active_profile": "blog_style"})

    return ActionResult.success(
        data={"profile_name": "blog_style", "posts_analyzed": posts_count},
        summary=(
            f"Blog style analyzed from {posts_count} posts at {blog_url}.\n"
            "Profile 'blog_style' created and set as active — all new articles will follow this style."
        ),
        ui=ui.Stack(children=[
            ui.Alert(
                message=f"Writing style set from {blog_url} ({posts_count} posts analyzed). "
                        "Profile 'blog_style' is now active.",
                type="success",
            ),
            ui.Text(content=profile_text[:600] + "...", variant="caption"),
        ]),
    )


# ── Google Search Console handlers ────────────────────────────────────────────

from pydantic import BaseModel as _BM


class EmptyGSCParams(_BM):
    pass


class GSCPageParams(_BM):
    page_url: str = ""


@chat.function(
    "gsc_report",
    description=(
        "Show Google Search Console (GSC) report: clicks, impressions, CTR, avg position, "
        "top pages, top queries, anomalies (traffic spikes/drops), growth opportunities. "
        "ALWAYS use for: GSC отчёт, покажи GSC, клики из Google, позиции в поиске, "
        "аномалии трафика, что падает, что растёт, трафик из поиска, "
        "google search console, покажи органику, gsc данные, "
        "какие статьи выросли, какие статьи падают, вокруг каких кейвордов растут статьи, "
        "blog статьи трафик из поиска, которые статьи хорошо ранжируются, "
        "какие страницы теряют трафик, где теряю клики, SEO трафик отчёт."
    ),
    action_type="read",
    event="gsc.report",
    data_model=GenericPayloadResponse,
)
async def gsc_report(ctx, params: EmptyGSCParams) -> ActionResult:
    try:
        s = await load_settings(ctx)
    except Exception as e:
        return ActionResult.success(data={"error": "load"}, summary=f"GSC load_settings failed: {e}")
    if not gsc_ready(s):
        return ActionResult.success(
            data={"error": "not_connected"},
            summary="GSC not connected — open Settings → Google Search Console and paste your credentials JSON to connect.",
        )

    try:
        verify = await gsc_verify(ctx)
    except Exception as e:
        return ActionResult.success(data={"error": "verify"}, summary=f"GSC verify exception: {e}")
    if not verify.get("ok"):
        err = verify.get("error", "unknown error")
        return ActionResult.success(
            data={"error": "verify_failed", "detail": err},
            summary=f"GSC connection check failed: {err}. Try reconnecting in Settings.",
        )

    try:
        payload = _gsc_auth_payload(s)
    except Exception as e:
        return ActionResult.success(data={"error": "payload"}, summary=f"GSC payload build failed: {e}")

    # Try stored site_url first; if returns 0 pages fall back to sc-domain
    site_url = s.get("gsc_site_url", "")
    fallback_domain = "sc-domain:webhostmost.com"
    if site_url and site_url != fallback_domain and "webhostmost.com" in site_url:
        test = await _post(ctx, "/api/gsc/pages", payload)
        if not isinstance(test, Exception) and not test.get("pages"):
            payload = {**payload, "site_url": fallback_domain}

    pages_data, queries_data, anomalies_data, opps_data = await asyncio.gather(
        _post(ctx, "/api/gsc/pages", payload),
        _post(ctx, "/api/gsc/top-queries", payload),
        _post(ctx, "/api/gsc/anomalies", payload),
        _post(ctx, "/api/gsc/growth-opportunities", payload),
        return_exceptions=True,
    )

    def safe(r):
        return r if not isinstance(r, Exception) else {}

    pages     = safe(pages_data).get("pages", [])[:10]
    queries   = safe(queries_data).get("queries", [])[:10]
    anomalies = safe(anomalies_data).get("anomalies", [])[:8]
    opps      = safe(opps_data).get("opportunities", [])[:8]

    total_clicks = sum(p.get("clicks", 0) for p in pages)
    total_impr   = sum(p.get("impressions", 0) for p in pages)

    pages_table = ui.DataTable(
        columns=[
            ui.DataColumn(key="url",    label="Page URL",   width="50%"),
            ui.DataColumn(key="clicks", label="Clicks",     width="12%"),
            ui.DataColumn(key="impr",   label="Impr.",      width="12%"),
            ui.DataColumn(key="ctr",    label="CTR%",       width="12%"),
            ui.DataColumn(key="pos",    label="Avg Pos",    width="14%"),
        ],
        rows=[{
            "url":    p["url"].replace("https://blog.webhostmost.com", "").replace("https://webhostmost.com", "") or "/",
            "clicks": str(p.get("clicks", 0)),
            "impr":   str(p.get("impressions", 0)),
            "ctr":    f"{p.get('ctr', 0):.1f}%",
            "pos":    f"{p.get('position', 0):.1f}",
        } for p in pages],
    ) if pages else None

    anomaly_items = [
        ui.Stack(direction="h", gap=2, children=[
            ui.Badge(
                label=f"{'↑' if a['type']=='spike' else '↓'} {abs(int(a.get('change_pct', 0)))}%",
                color="green" if a["type"] == "spike" else "red",
            ),
            ui.Text(content=a["url"].replace("https://blog.webhostmost.com","").replace("https://webhostmost.com","")[:60], variant="caption"),
        ])
        for a in anomalies
    ] if anomalies else [ui.Text(content="No significant anomalies detected.", variant="caption")]

    opp_items = [
        ui.Text(
            content=f"{o['url'].replace('https://blog.webhostmost.com','')[:50]}  — {o['impressions']} impr, pos {o['position']:.0f}, CTR {o['ctr']:.1f}% → {o['recommendation']}",
            variant="caption",
        )
        for o in opps
    ] if opps else [ui.Text(content="No opportunities found (GSC data may be limited).", variant="caption")]

    report_ui = ui.Stack(children=[
        ui.Stack(direction="h", gap=3, children=[
            ui.Stat(label="Total Clicks (90d)", value=f"{total_clicks:,}", color="blue"),
            ui.Stat(label="Impressions",        value=f"{total_impr:,}",  color="gray"),
        ]),
        ui.Section(title="Top Pages by Clicks", collapsible=False, children=[pages_table] if pages_table else [ui.Text(content="No data.", variant="caption")]),
        ui.Section(title="Anomalies (traffic spikes/drops vs baseline)", collapsible=True, children=anomaly_items),
        ui.Section(title="Growth Opportunities (high impr, low CTR)", collapsible=True, children=opp_items),
    ])

    # Build rich summary with actual article URLs so Webbee can present them in chat
    blog_pages = [p for p in pages if "blog.webhostmost.com" in p.get("url", "")]
    blog_opps  = [o for o in opps  if "blog.webhostmost.com" in o.get("url", "")]

    pages_lines = "\n".join(
        f"  {p['url'].replace('https://blog.webhostmost.com','')}: {p.get('clicks',0)} clicks, pos {p.get('position',0):.1f}"
        for p in blog_pages[:8]
    ) or "\n".join(
        f"  {p['url'][:70]}: {p.get('clicks',0)} clicks, pos {p.get('position',0):.1f}"
        for p in pages[:8]
    )

    opps_lines = "\n".join(
        f"  {o['url'].replace('https://blog.webhostmost.com','')}: {o.get('impressions',0):,} impr, pos {o.get('position',0):.0f} → {o.get('recommendation','')}"
        for o in blog_opps[:8]
    ) or "\n".join(
        f"  {o['url'][:70]}: {o.get('impressions',0):,} impr → {o.get('recommendation','')}"
        for o in opps[:8]
    )

    top_queries_text = "\n".join(
        f"  \"{q.get('query','')}\": {q.get('clicks',0)} clicks, pos {q.get('position',0):.1f}"
        for q in queries[:8]
    ) if queries else "  (no query data)"

    return ActionResult.success(
        data={"total_clicks": total_clicks, "total_impressions": total_impr,
              "anomalies": len(anomalies), "opportunities": len(opps),
              "blog_pages": blog_pages, "blog_opportunities": blog_opps},
        summary=(
            f"GSC Report — sc-domain:webhostmost.com\n"
            f"Total: {total_clicks:,} clicks | {total_impr:,} impressions | CTR {total_clicks/max(total_impr,1)*100:.1f}%\n\n"
            f"TOP BLOG ARTICLES (by clicks):\n{pages_lines}\n\n"
            f"TOP SEARCH QUERIES:\n{top_queries_text}\n\n"
            f"GROWTH OPPORTUNITIES (high impressions, needs CTR boost):\n{opps_lines}\n\n"
            f"Anomalies: {len(anomalies)} | Opportunities: {len(opps)}"
        ),
        ui=report_ui,
    )


class GSCOAuthParams(_BM):
    credentials_json: str  # authorized_user JSON or client_secrets.json
    auth_code: str = ""
    site_url: str = ""


@chat.function(
    "gsc_connect_oauth",
    description=(
        "Connect GSC via Google OAuth2 using credentials.json from Google Cloud. "
        "Step 1: user pastes contents of credentials.json file, gets auth URL. "
        "Step 2: user visits URL, authorizes, pastes auth code — system saves authorized credentials. "
        "Use when: 'подключи GSC через гугл аккаунт', 'OAuth GSC', 'give me GSC auth link'. "
        "If auth_code is empty — returns auth URL. If auth_code is provided — exchanges and saves."
    ),
    action_type="write",
)
async def gsc_connect_oauth(ctx, params: GSCOAuthParams) -> ActionResult:
    creds_json = params.credentials_json.strip()
    if not creds_json:
        return ActionResult.error(error="Paste your credentials.json content from Google Cloud Console.")

    # Direct save: if credentials_json is already authorized_user type, save immediately
    import json as _json
    try:
        _parsed = _json.loads(creds_json)
        if _parsed.get("type") == "authorized_user" and _parsed.get("refresh_token"):
            s = await load_settings(ctx)
            await save_settings(ctx, {
                "gsc_credentials_json": creds_json,
                "gsc_site_url": params.site_url or s.get("gsc_site_url", "https://webhostmost.com"),
            })
            return ActionResult.success(
                data={"connected": True},
                summary=f"GSC connected for {params.site_url or s.get('gsc_site_url', 'webhostmost.com')}. Run 'покажи GSC отчёт' to see data.",
                refresh_panels=["sidebar"],
            )
    except Exception:
        pass

    # Step 2: exchange code if provided
    if params.auth_code.strip():
        result = await _post(ctx, "/api/gsc/oauth-exchange", {
            "credentials_json": creds_json,
            "auth_code": params.auth_code.strip(),
        })
        if not result.get("ok"):
            return ActionResult.error(error=f"Token exchange failed: {result.get('error', 'unknown')}")

        authorized = result.get("authorized_credentials", "")
        if not authorized:
            return ActionResult.error(error="No credentials returned. Try again.")

        await save_settings(ctx, {"gsc_credentials_json": authorized})
        return ActionResult.success(
            data={"connected": True},
            summary="GSC connected! Authorized credentials saved. Run 'gsc report' to see your data.",
            refresh_panels=["sidebar"],
        )

    # Step 1: generate auth URL
    result = await _post(ctx, "/api/gsc/oauth-authorize", {
        "site_url": (await load_settings(ctx)).get("gsc_site_url", ""),
        "credentials_json": creds_json,
    })
    if not result.get("ok"):
        return ActionResult.error(error=f"Failed: {result.get('error', result)}")

    return ActionResult.success(
        data={"auth_url": result["auth_url"]},
        summary=(
            "Step 2 — open this link and authorize:\n"
            f"{result['auth_url']}\n\n"
            "Then tell me:\n"
            "gsc_connect_oauth credentials_json=<same JSON> auth_code=<code from Google>"
        ),
    )


class _GSCCredsParams(_BM):
    site_url: str
    credentials_json: str


@chat.function(
    "save_gsc_credentials",
    description="Save GSC credentials directly to settings. Use: site_url=URL credentials_json=JSON",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
)
async def save_gsc_credentials(ctx, params: _GSCCredsParams) -> ActionResult:
    await save_settings(ctx, {
        "gsc_site_url": params.site_url,
        "gsc_credentials_json": params.credentials_json,
    })
    return ActionResult.success(
        data={"saved": True},
        summary=f"GSC connected for {params.site_url}. Run 'gsc_report' to test.",
        refresh_panels=["sidebar"],
    )
