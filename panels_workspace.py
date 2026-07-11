"""Main workspace panel — plan | editor | rankings | keywords | settings."""
from __future__ import annotations

import asyncio

from imperal_sdk import ui

from wpb_app import ext, load_settings, load_ui_state, save_ui_state, list_content, get_content, ser_ready, wp_ready, gsc_ready
from api_client import gsc_pages
from panels_editor import editor_view
from panels_docs import _docs_view
from panels_settings_view import _settings_view
from handlers_docs import _load_docs

REFRESH = "on_event:seo.content.updated"


@ext.panel("editor", slot="center", title="SEO & Content", icon="FileText",
           refresh=REFRESH, center_overlay=True)
async def workspace_panel(ctx, active_view: str = "", plan_filter: str = "", content_id: str = "", **_kw):
    # SDK 5.0: note_id may not arrive via **_kw — default to "plan" view
    # instead of returning None which causes infinite Loading... spinner
    if not content_id and not active_view:
        active_view = "plan"

    state = await load_ui_state(ctx)
    if content_id:
        _opened_item = await get_content(ctx, content_id)
        _kw_label = ((_opened_item.get("keyword") or _opened_item.get("title") or content_id[:12]) if _opened_item else content_id[:12])[:28]
        await save_ui_state(ctx, {"active_view": "editor", "selected_id": content_id, "last_opened_keyword": _kw_label})
        state = await load_ui_state(ctx)
    elif active_view:
        updates: dict = {"active_view": active_view}
        if plan_filter:
            updates["plan_filter"] = plan_filter
        editor_mode = _kw.get("editor_mode", "")
        if editor_mode:
            updates["editor_mode"] = editor_mode
        show_editor = _kw.get("show_editor", "")
        if show_editor != "":
            updates["show_editor_panel"] = show_editor == "1"
        await save_ui_state(ctx, updates)
        state = {**state, **updates}
    view = active_view or state.get("active_view", "plan")

    if view == "editor":
        return await editor_view(ctx, state)
    if view == "rankings":
        return await _rankings_view(ctx, state)
    if view == "keywords":
        return await _keywords_view(ctx, state)
    if view == "settings":
        return await _settings_view(ctx)
    if view == "docs":
        return await _docs_view(ctx, await _load_docs(ctx))
    return await _plan_view(ctx, state)


# ── Plan view ─────────────────────────────────────────────────────────────────

_STATUS_COLOR = {"idea": "gray", "writing": "blue", "review": "yellow", "published": "green"}
_STATUS_ICON  = {"idea": "Lightbulb", "writing": "PenLine", "review": "Eye", "published": "CheckCircle"}


def _back_btn() -> ui.UINode:
    return ui.Button(
        label="← Back",
        size="sm",
        variant="ghost",
        on_click=ui.Call("__panel__editor", active_view="plan", note_id="board"),
    )


def _vol_str(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000: return f"{v/1_000:.0f}K"
    return str(v) or "0"

async def _plan_view(ctx, state: dict) -> ui.UINode:
    items = await list_content(ctx)
    plan_filter = state.get("plan_filter") or "all"
    filtered = [i for i in items if i.get("status") == plan_filter] if plan_filter not in ("all", "") else items

    # GSC pages index (url → stats) — fetched once, used per row
    # Timeout 8s: if GSC is slow, skip badges and render anyway
    gsc_index = {}
    _settings = await load_settings(ctx)
    if gsc_ready(_settings):
        try:
            _gsc_resp = await asyncio.wait_for(gsc_pages(ctx), timeout=8.0)
            for _p in _gsc_resp.get("pages", []):
                gsc_index[_p["url"].rstrip("/")] = _p
        except Exception:
            pass

    # ── Metrics ───────────────────────────────────────────────────────────────
    counts = {s: sum(1 for i in items if i.get("status") == s)
              for s in ("idea", "writing", "review", "published")}
    total_words  = sum(len((i.get("content") or "").split()) for i in items)
    in_wp        = sum(1 for i in items if i.get("wp_post_id"))
    total_volume = sum(i.get("volume") or 0 for i in items)

    # ── Stats row ─────────────────────────────────────────────────────────────
    stats = ui.Stats(children=[
        ui.Stat(label="Total articles", value=str(len(items)),    icon="FileText"),
        ui.Stat(label="Ideas",          value=str(counts["idea"]),       color="gray",   icon="Lightbulb"),
        ui.Stat(label="Writing",        value=str(counts["writing"]),    color="blue",   icon="PenLine"),
        ui.Stat(label="In review",      value=str(counts["review"]),     color="yellow", icon="Eye"),
        ui.Stat(label="Published",      value=str(counts["published"]),  color="green",  icon="CheckCircle"),
        ui.Stat(label="Words written",  value=f"{total_words:,}",        icon="Hash"),
        ui.Stat(label="In WordPress",   value=str(in_wp),                icon="Globe"),
        ui.Stat(label="Total volume",   value=_vol_str(total_volume),    icon="TrendingUp"),
    ]) if items else ui.Alert(message="No content yet. Build a content plan or add items from the left sidebar.", type="info")

    # ── Pipeline funnel chart ─────────────────────────────────────────────────
    funnel_data = [
        {"label": "Ideas",     "value": counts["idea"]},
        {"label": "Writing",   "value": counts["writing"]},
        {"label": "Review",    "value": counts["review"]},
        {"label": "Published", "value": counts["published"]},
    ]
    pipeline_chart = ui.Section(title="Content Pipeline", collapsible=False, children=[
        ui.Chart(
            type="bar",
            data=funnel_data,
            x_key="label",
            y2_keys=["value"],
            colors={"value": "#6366f1"},
            height=120,
        ),
    ]) if items else None

    # ── Filter buttons ────────────────────────────────────────────────────────
    def _filter_btn(label: str, status: str, count: int) -> ui.UINode:
        active = plan_filter == status
        return ui.Button(
            label=f"{label} · {count}",
            on_click=ui.Call("__panel__editor", active_view="plan", plan_filter=status, note_id="board"),
            variant="secondary" if active else "ghost",
            size="sm",
        )

    filter_row = ui.Stack(direction="h", gap=2, children=[
        ui.Button(label="All", size="sm",
                  variant="secondary" if plan_filter in ("all", "") else "ghost",
                  on_click=ui.Call("__panel__editor", active_view="plan", note_id="board")),
        _filter_btn("Ideas",     "idea",      counts["idea"]),
        _filter_btn("Writing",   "writing",   counts["writing"]),
        _filter_btn("Review",    "review",    counts["review"]),
        _filter_btn("Published", "published", counts["published"]),
    ])

    # ── Article list — each row has direct "Open →" button (no Form/Save) ────
    _filter_label = {"idea": "Ideas", "writing": "Writing", "review": "Review", "published": "Published"}
    title = f"Content — {_filter_label.get(plan_filter, 'All')}" if plan_filter not in ("all", "") else f"All Content ({len(items)})"

    def _article_row(item: dict) -> ui.UINode:
        status     = item.get("status", "idea")
        word_count = len((item.get("content") or "").split())
        vol        = f"{item.get('volume', 0):,}" if item.get("volume") else "—"
        diff       = f"{item.get('difficulty', 0):.0f}" if item.get("difficulty") else "—"
        wp_badge   = "  WP✓" if item.get("wp_post_id") else ""

        gsc_badge_node = None
        url = (item.get("target_url") or "").rstrip("/")
        if url and gsc_index:
            g = gsc_index.get(url)
            if g and g.get("clicks", 0) > 0:
                gsc_badge_node = ui.Badge(
                    label=f"🔍 {g['clicks']} clicks · pos {g.get('position', 0):.0f}",
                    color="blue",
                )

        item_id = item.get("id", "")
        return ui.Stack(direction="h", gap=2, align="center", children=[
            ui.Stack(children=[
                ui.Text(content=item.get("keyword", "—")[:50]),
                ui.Text(
                    content=f"{item.get('type','blog')} · {word_count}w · Vol:{vol} · Diff:{diff}{wp_badge}",
                    variant="caption",
                ),
            ]),
            ui.Badge(label=status, color=_STATUS_COLOR.get(status, "gray")),
            *([ gsc_badge_node ] if gsc_badge_node else []),
            ui.Button(
                label="Open →",
                size="sm",
                variant="secondary",
                on_click=ui.Call("__panel__editor", content_id=item_id, note_id="board"),
            ),
            ui.Button(
                label="✕",
                size="sm",
                variant="ghost",
                on_click=ui.Call("delete_content", content_id=item_id),
            ),
        ])

    table = ui.Stack(children=[_article_row(i) for i in filtered]) if filtered else ui.Empty(
        message=f"No {_filter_label.get(plan_filter,'').lower()} items." if plan_filter not in ("all","") else "No content yet — build a plan or add items."
    )

    # ── Header ────────────────────────────────────────────────────────────────
    header = ui.Stack(direction="h", justify="between", align="center", children=[
        ui.Stack(direction="h", gap=2, children=[
            ui.Button(label="← Webbee", size="sm", variant="ghost",
                      on_click=ui.Navigate("/")),
            ui.Header(text=title, level=3),
        ]),
        ui.Stack(direction="h", gap=2, children=[
            ui.Button(label="🔍 Keywords", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__editor", active_view="keywords", note_id="board")),
            ui.Button(label="📊 Rankings", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__editor", active_view="rankings", note_id="board")),
        ]),
    ])

    build_btn = ui.Form(action="build_content_plan", submit_label="✨ Build Content Plan (AI)", children=[])

    # ── SEO Potential block — top keywords by volume ──────────────────────────
    top_by_vol = sorted([i for i in items if i.get("volume", 0) > 0],
                        key=lambda x: -(x.get("volume") or 0))[:5]
    potential_section = ui.Section(
        title=f"🎯 SEO Potential — top {len(top_by_vol)} by search volume",
        collapsible=True,
        children=[
            ui.DataTable(
                columns=[
                    ui.DataColumn(key="kw",     label="Keyword",  width="45%"),
                    ui.DataColumn(key="vol",    label="Vol/mo",   width="15%"),
                    ui.DataColumn(key="diff",   label="Diff",     width="10%"),
                    ui.DataColumn(key="status", label="Status",   width="15%"),
                    ui.DataColumn(key="type",   label="Type",     width="15%"),
                ],
                rows=[
                    {
                        "kw":     i.get("keyword","")[:40],
                        "vol":    f"{i.get('volume',0):,}",
                        "diff":   str(i.get("difficulty","—")),
                        "status": i.get("status","idea"),
                        "type":   i.get("type","blog"),
                    }
                    for i in top_by_vol
                ],
            ),
        ],
    ) if top_by_vol else None

    # ── Progress overview ─────────────────────────────────────────────────────
    written = counts["writing"] + counts["review"] + counts["published"]
    total   = len(items)
    pct     = int(written / total * 100) if total else 0
    progress_stats = ui.Stats(children=[
        ui.Stat(label="Written",         value=f"{written}/{total}", color="blue",  icon="PenLine"),
        ui.Stat(label="Published in WP", value=str(in_wp),           color="green", icon="Globe"),
        ui.Stat(label="Total words",     value=f"{total_words:,}",   icon="Hash"),
        ui.Stat(label="SEO volume",      value=_vol_str(total_volume), color="yellow", icon="TrendingUp"),
        ui.Stat(label="Progress",        value=f"{pct}%",             color="green" if pct > 50 else "yellow", icon="BarChart2"),
    ]) if items else None

    # ── Quick-add idea form ───────────────────────────────────────────────────
    quick_add = ui.Form(
        action="new_content",
        submit_label="+ Add Idea",
        children=[
            ui.Stack(direction="h", gap=8, children=[
                ui.Input(param_name="keyword", placeholder="Keyword or topic"),
                ui.Select(
                    param_name="type",
                    options=[
                        {"value": "blog",       "label": "Blog"},
                        {"value": "tutorial",   "label": "Tutorial"},
                        {"value": "review",     "label": "Review"},
                        {"value": "comparison", "label": "Comparison"},
                    ],
                ),
            ]),
        ],
    )

    children = [header, stats]
    if progress_stats:
        children.append(progress_stats)
    children += [build_btn, ui.Divider(), filter_row]
    if pipeline_chart:
        children.append(pipeline_chart)
    children.append(quick_add)
    children.append(table)
    if potential_section:
        children.append(potential_section)

    return ui.Stack(children=children)


# ── Rankings view ─────────────────────────────────────────────────────────────

async def _rankings_view(ctx, state: dict) -> ui.UINode:
    rankings  = state.get("rankings_results") or []
    ai_data   = state.get("ai_traffic") or {}
    refresh_btn = ui.Form(action="fetch_rankings", submit_label="↻ Refresh", children=[])

    if not rankings:
        return ui.Stack(children=[
            ui.Stack(direction="h", justify="between", children=[
                ui.Stack(direction="h", gap=2, children=[
                    _back_btn(),
                    ui.Header(text="📊 SEO Rankings", level=3),
                ]),
                refresh_btn,
            ]),
            ui.Alert(message="Нет данных. Нажми ↻ Refresh чтобы загрузить позиции из SE Ranking.", type="info"),
            ui.Form(action="fetch_rankings", submit_label="↻ Load Rankings", children=[]),
        ])

    # ── Compute metrics ────────────────────────────────────────────────────────
    ranked    = [r for r in rankings if r.get("position", 0) > 0]
    top3      = sum(1 for r in ranked if r.get("position", 99) <= 3)
    top10     = sum(1 for r in ranked if r.get("position", 99) <= 10)
    top30     = sum(1 for r in ranked if r.get("position", 99) <= 30)
    top100    = sum(1 for r in ranked if r.get("position", 99) <= 100)
    not_rank  = len(rankings) - len(ranked)
    total_vol = sum(r.get("volume", 0) for r in rankings)

    gainers, losers = [], []
    for r in ranked:
        prev = r.get("previous_position", 0)
        curr = r.get("position", 0)
        if prev and curr and prev != curr:
            change = prev - curr
            entry  = {**r, "_change": change}
            (gainers if change > 0 else losers).append(entry)
    gainers = sorted(gainers, key=lambda x: -x["_change"])[:8]
    losers  = sorted(losers,  key=lambda x:  x["_change"])[:8]

    # ── Good news callout ─────────────────────────────────────────────────────
    best_kws = sorted(ranked, key=lambda r: r.get("position", 999))[:3]
    net_gain  = len(gainers) - len(losers)
    net_arrow = "▲" if net_gain > 0 else ("▼" if net_gain < 0 else "—")
    net_color = "green" if net_gain > 0 else ("red" if net_gain < 0 else "gray")

    good_news = ui.Stats(children=[
        ui.Stat(label="Best position",   value=best_kws[0]["keyword"][:25] if best_kws else "—",
                color="green", icon="Star"),
        ui.Stat(label="Net movers",      value=f"{net_arrow} {abs(net_gain)}",
                color=net_color, icon="TrendingUp"),
        ui.Stat(label="Gainers today",   value=str(len(gainers)), color="green",  icon="ArrowUp"),
        ui.Stat(label="Losers today",    value=str(len(losers)),  color="red",    icon="ArrowDown"),
        ui.Stat(label="Monthly volume",  value=f"{_vol_str(total_vol)}", icon="Eye"),
    ])

    # ── Stats row ─────────────────────────────────────────────────────────────
    stats = ui.Stats(children=[
        ui.Stat(label="Tracked",    value=str(len(rankings)), icon="Target"),
        ui.Stat(label="Top 3  🟢",  value=str(top3),          color="green",  icon="TrendingUp"),
        ui.Stat(label="Top 10 🔵",  value=str(top10),         color="blue",   icon="Award"),
        ui.Stat(label="Top 30 🟡",  value=str(top30),         color="yellow", icon="BarChart2"),
        ui.Stat(label="Top 100",    value=str(top100),        color="gray",   icon="List"),
        ui.Stat(label="Not ranked 🔴", value=str(not_rank),   color="red",    icon="Minus"),
    ])

    pos_chart = ui.Section(title="Position Distribution", collapsible=False, children=[
        ui.Stats(children=[
            ui.Stat(label="🟢 Top 3",      value=str(top3),          color="green"),
            ui.Stat(label="🔵 4–10",       value=str(top10-top3),    color="blue"),
            ui.Stat(label="🟡 11–30",      value=str(top30-top10),   color="yellow"),
            ui.Stat(label="🟠 31–100",     value=str(top100-top30),  color="gray"),
            ui.Stat(label="🔴 Not ranked", value=str(not_rank),      color="red"),
        ]),
        ui.Chart(
            type="bar",
            data=[
                {"label": "Top 3",      "value": top3},
                {"label": "4–10",       "value": top10 - top3},
                {"label": "11–30",      "value": top30 - top10},
                {"label": "31–100",     "value": top100 - top30},
                {"label": "Not ranked", "value": not_rank},
            ],
            x_key="label",
            y2_keys=["value"],
            colors={"value": "#6366f1"},
            height=120,
        ),
    ])

    # ── AI Traffic section ────────────────────────────────────────────────────
    ai_sources    = ai_data.get("sources", [])
    ai_total      = ai_data.get("total_visits", 0)
    ai_change_pct = ai_data.get("total_change_pct", 0)
    ai_sign       = "+" if ai_change_pct >= 0 else ""

    if ai_sources:
        ai_chart_data = [{"label": s["source"], "value": s["visits"]} for s in ai_sources[:8] if s["visits"] > 0]
        ai_rows = [
            {
                "source":  s["source"],
                "visits":  str(s["visits"]),
                "prev":    str(s["prev_visits"]),
                "change":  f"{'+' if s['change'] >= 0 else ''}{s['change_pct']}%",
                "trend":   "▲" if s["trend"] == "up" else ("▼" if s["trend"] == "down" else "—"),
            }
            for s in ai_sources
        ]
        ai_section = ui.Section(
            title=f"🤖 AI Traffic — {ai_total} visits ({ai_sign}{ai_change_pct}% vs last month)",
            collapsible=False,
            children=[
                ui.Text(content="Traffic from ChatGPT, Perplexity, Gemini, Claude and other AI sources.", variant="caption"),
                ui.Chart(type="bar", data=ai_chart_data, x_key="label",
                         y2_keys=["value"], colors={"value": "#8b5cf6"}, height=140)
                if ai_chart_data else ui.Empty(message="No chart data"),
                ui.DataTable(
                    columns=[
                        ui.DataColumn(key="source", label="AI Source", width="30%"),
                        ui.DataColumn(key="visits", label="Visits",    width="15%"),
                        ui.DataColumn(key="prev",   label="Last mo.",  width="15%"),
                        ui.DataColumn(key="change", label="Change",    width="20%"),
                        ui.DataColumn(key="trend",  label="↕",         width="10%"),
                    ],
                    rows=ai_rows,
                ),
            ],
        )
    else:
        ai_section = ui.Section(
            title="🤖 AI Traffic",
            collapsible=True,
            children=[
                ui.Alert(
                    message="No AI referrer traffic this month (ChatGPT, Perplexity, Gemini). Data via Analytics extension.",
                    type="info",
                ),
            ],
        )

    # ── Top movers ────────────────────────────────────────────────────────────
    def _gainer_rows(items: list) -> list:
        return [
            {"pos": str(r.get("position","—")), "chg": f"▲ +{r['_change']}",
             "keyword": r.get("keyword","—")[:35], "vol": f"{r.get('volume',0):,}" if r.get("volume") else "—"}
            for r in items
        ]

    def _loser_rows(items: list) -> list:
        return [
            {"pos": str(r.get("position","—")), "chg": f"▼ -{abs(r['_change'])}",
             "keyword": r.get("keyword","—")[:35], "vol": f"{r.get('volume',0):,}" if r.get("volume") else "—"}
            for r in items
        ]

    mover_cols = [
        ui.DataColumn(key="pos",     label="#",       width="8%"),
        ui.DataColumn(key="chg",     label="±",       width="16%"),
        ui.DataColumn(key="keyword", label="Keyword", width="56%"),
        ui.DataColumn(key="vol",     label="Vol",     width="20%"),
    ]

    gainer_chart_data = [{"label": r.get("keyword","")[:15], "gain": r["_change"]} for r in gainers[:6] if r["_change"] > 0]
    loser_chart_data  = [{"label": r.get("keyword","")[:15], "loss": abs(r["_change"])} for r in losers[:6]]

    movers = ui.Stack(direction="h", gap=3, children=[
        ui.Section(title=f"🟢 Gainers ({len(gainers)})", collapsible=False, children=[
            ui.Chart(type="bar", data=gainer_chart_data, x_key="label",
                     y2_keys=["gain"], colors={"gain": "#22c55e"}, height=100)
            if gainer_chart_data else ui.Empty(message=""),
            ui.DataTable(columns=mover_cols, rows=_gainer_rows(gainers))
            if gainers else ui.Text(content="No gainers this period", variant="caption"),
        ]),
        ui.Section(title=f"🔴 Losers ({len(losers)})", collapsible=False, children=[
            ui.Chart(type="bar", data=loser_chart_data, x_key="label",
                     y2_keys=["loss"], colors={"loss": "#ef4444"}, height=100)
            if loser_chart_data else ui.Empty(message=""),
            ui.DataTable(columns=mover_cols, rows=_loser_rows(losers))
            if losers else ui.Text(content="No losers this period", variant="caption"),
        ]),
    ])

    # ── Full keyword table ────────────────────────────────────────────────────
    all_rows = [
        {
            "pos":  str(r.get("position") or "—"),
            "chg":  ("▲" if (r.get("previous_position") or 0) > (r.get("position") or 0)
                     else "▼" if (r.get("previous_position") or 0) < (r.get("position") or 0)
                     else "—") if r.get("previous_position") else "—",
            "kw":   r.get("keyword", "—"),
            "url":  (r.get("url") or "")[-40:],
            "vol":  f"{r.get('volume', 0):,}" if r.get("volume") else "—",
            "diff": f"{r.get('difficulty', 0):.0f}" if r.get("difficulty") else "—",
        }
        for r in sorted(rankings, key=lambda x: x.get("position") or 9999)[:200]
    ]
    full_table = ui.Section(
        title=f"All Keywords ({len(rankings)}) — sorted by position",
        collapsible=True,
        children=[
            ui.DataTable(
                columns=[
                    ui.DataColumn(key="pos",  label="#",        width="6%"),
                    ui.DataColumn(key="chg",  label="±",        width="5%"),
                    ui.DataColumn(key="kw",   label="Keyword",  width="38%"),
                    ui.DataColumn(key="url",  label="Page",     width="30%"),
                    ui.DataColumn(key="vol",  label="Vol",      width="12%"),
                    ui.DataColumn(key="diff", label="Diff",     width="9%"),
                ],
                rows=all_rows,
            ),
        ],
    )

    return ui.Stack(children=[
        ui.Stack(direction="h", justify="between", align="center", children=[
            ui.Stack(direction="h", gap=2, children=[
                _back_btn(),
                ui.Header(text="📊 SEO Rankings", level=3),
            ]),
            refresh_btn,
        ]),
        good_news,
        stats,
        pos_chart,
        ai_section,
        movers,
        full_table,
    ])


# ── Keywords view ─────────────────────────────────────────────────────────────

async def _keywords_view(ctx, state: dict) -> ui.UINode:
    kws = state.get("kw_results") or []

    search_form = ui.Form(
        action="fetch_keywords",
        submit_label="Search keywords",
        children=[
            ui.Input(param_name="domain", placeholder="Domain (default: blog.webhostmost.com)"),
            ui.Input(param_name="min_volume", placeholder="Min volume (default: 100)"),
            ui.Input(param_name="max_difficulty", placeholder="Max difficulty (default: 60)"),
            ui.Input(param_name="limit", placeholder="Limit (default: 50)"),
        ],
    )

    gap_form = ui.Form(
        action="fetch_gaps",
        submit_label="Find gaps vs competitor",
        children=[
            ui.Input(param_name="competitor", placeholder="Competitor domain (e.g. hostinger.com)"),
            ui.Input(param_name="limit", placeholder="Limit (default: 30)"),
        ],
    )

    if not kws:
        return ui.Stack(children=[
            ui.Stack(direction="h", justify="between", align="center", children=[
                ui.Header(text="🔍 Keyword Research", level=3),
                _back_btn(),
            ]),
            search_form,
            ui.Divider(),
            gap_form,
        ])

    rows = [
        {
            "keyword": k.get("keyword", "—"),
            "pos": str(k.get("position", "—")),
            "volume": f"{k.get('volume', 0):,}",
            "diff": str(k.get("difficulty", "—")),
            "cpc": f"${k.get('cpc', 0):.2f}" if k.get("cpc") else "—",
        }
        for k in kws[:100]
    ]

    add_form = ui.Form(
        action="new_content",
        submit_label="Add to content plan",
        children=[
            ui.Input(param_name="keyword", placeholder="Paste keyword from table above"),
            ui.Select(param_name="type", placeholder="Type", options=[
                {"value": "blog", "label": "Blog post"},
                {"value": "newsletter", "label": "Newsletter"},
            ]),
            ui.Input(param_name="volume", placeholder="Volume"),
            ui.Input(param_name="difficulty", placeholder="Difficulty"),
        ],
    )

    return ui.Stack(children=[
        ui.Stack(direction="h", justify="between", align="center", children=[
            ui.Header(text="🔍 Keyword Research", level=3),
            _back_btn(),
        ]),
        search_form,
        ui.Divider(),
        gap_form,
        ui.Divider(),
        ui.Text(content=f"{len(kws)} keywords found", variant="caption"),
        ui.DataTable(
            columns=[
                ui.DataColumn(key="keyword", label="Keyword", width="40%"),
                ui.DataColumn(key="pos", label="Pos", width="8%"),
                ui.DataColumn(key="volume", label="Volume", width="16%"),
                ui.DataColumn(key="diff", label="Diff", width="10%"),
                ui.DataColumn(key="cpc", label="CPC", width="12%"),
            ],
            rows=rows,
        ),
        ui.Divider(),
        add_form,
    ])
