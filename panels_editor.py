"""Editor view — clean step-by-step UX. All handlers read content_id from UI state."""
from __future__ import annotations

from imperal_sdk import ui

from wpb_app import get_content, load_settings, gsc_ready
from api_client import gsc_page_detail
from panels_editor_helpers import _brief_html, _article_html
from panels_editor_newsletter import _newsletter_editor

STATUS_COLOR = {
    "idea":      "gray",
    "writing":   "blue",
    "review":    "yellow",
    "published": "green",
}


async def editor_view(ctx, state: dict) -> ui.UINode:
    content_id = state.get("selected_id")
    mode = state.get("editor_mode", "edit")

    if not content_id:
        return ui.Alert(message="No item selected. Go to Content Plan and open an item.", type="warning")

    item = await get_content(ctx, content_id)
    if not item:
        return ui.Alert(message=f"Item {content_id} not found.", type="error")

    if item.get("type") == "newsletter":
        return _newsletter_editor(item, mode)

    s = await load_settings(ctx)
    wp_base_url = s.get("wp_url", "").rstrip("/")

    gsc_data = {}
    target_url = item.get("target_url", "")
    if gsc_ready(s) and target_url:
        try:
            gsc_data = await gsc_page_detail(ctx, target_url)
        except Exception:
            pass

    return _blog_editor(item, mode, wp_base_url, show_editor=state.get("show_editor", False), gsc_data=gsc_data)


# ── Blog editor ───────────────────────────────────────────────────────────────

def _blog_editor(item: dict, mode: str, wp_base_url: str = "", show_editor: bool = False, gsc_data: dict = None) -> ui.UINode:
    kw           = item.get("keyword", "")
    title        = item.get("title", "")
    content_html = item.get("content", "")
    brief_text   = item.get("brief", "")
    status       = item.get("status", "idea")
    wp_id        = item.get("wp_post_id")
    wp_url       = item.get("target_url", "")
    meta_desc    = item.get("meta_description", "")
    focus_kw     = item.get("focus_keyword", "") or kw

    has_content = bool(content_html and len(content_html.strip()) > 100)

    # ── Header ────────────────────────────────────────────────────────────────
    toggle_btn = ui.Button(label="Preview", on_click=ui.Call("__panel__editor", active_view="editor", editor_mode="preview", note_id="board")) \
        if mode == "edit" else \
        ui.Button(label="← Edit", on_click=ui.Call("__panel__editor", active_view="editor", editor_mode="edit", note_id="board"))

    header = ui.Stack(children=[
        ui.Stack(children=[
            ui.Button(label="← Plan", on_click=ui.Call("__panel__editor", active_view="plan", note_id="board")),
            ui.Header(text=title or kw, level=3),
            ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
        ], direction="h", gap=8),
        toggle_btn,
    ], direction="h", justify="between")

    meta = ui.Stack(children=[
        ui.Text(content=f"Keyword: {kw}  ·  Volume: {item.get('volume', 0):,}/mo  ·  Difficulty: {item.get('difficulty', '—')}/100", variant="caption"),
    ])

    # ── Step 1: AI Brief ──────────────────────────────────────────────────────
    step1_children = [
        ui.Text(content="AI builds an SEO outline: title, meta description, H2/H3 structure, search intent.", variant="caption"),
        ui.Form(
            action="generate_brief",
            submit_label="Generate Brief",
            children=[
                ui.Input(param_name="extra", placeholder="Extra context (optional) — e.g. 'focus on VPS for developers'"),
            ],
        ),
    ]
    if brief_text:
        step1_children += [
            ui.Divider(),
            ui.Html(content=_brief_html(brief_text), sandbox=True),
            ui.Divider(),
            ui.Text(content="Edit brief below if needed, then Save:", variant="caption"),
            ui.Form(
                action="save_brief",
                submit_label="Save brief",
                children=[
                    ui.TextArea(param_name="brief_text", value=brief_text, rows=8),
                ],
            ),
            ui.Form(action="generate_brief", submit_label="Regenerate Brief", children=[]),
        ]
    step1 = ui.Section(
        title=f"Step 1 — Brief {'✓' if brief_text else '(optional)'}",
        children=step1_children,
    )

    # ── Step 2: AI Write ──────────────────────────────────────────────────────
    article_type = item.get("type", "blog")
    generating   = item.get("generating", False)
    type_options = [
        {"value": "blog",       "label": "Blog post (informational)"},
        {"value": "comparison", "label": "Comparison / X vs Y"},
        {"value": "tutorial",   "label": "Tutorial / step-by-step"},
        {"value": "pillar",     "label": "Pillar page (comprehensive)"},
        {"value": "news",       "label": "News / announcement"},
        {"value": "review",     "label": "Product / service review"},
    ]

    if generating:
        step2 = ui.Section(
            title="Step 2 — Writing article...",
            children=[
                ui.Loading(),
                ui.Text(content="Generation takes ~60-90 seconds. Click below to check.", variant="caption"),
                ui.Form(action="check_article_job", submit_label="Check result →", children=[]),
            ],
        )
    else:
        step2_children = [
            ui.Text(content="AI writes the full article. Run Brief first for better results.", variant="caption"),
            ui.Form(
                action="ai_write",
                submit_label="Write Full Article",
                children=[
                    ui.Select(
                        param_name="article_type",
                        placeholder=f"Article type: {article_type}",
                        options=type_options,
                    ),
                ],
            ),
        ]
        if has_content:
            step2_children.append(
                ui.Form(action="improve_article", submit_label="Improve Article", children=[])
            )
        step2 = ui.Section(title="Step 2 — Write with AI", children=step2_children)

    # ── Step 3: Editor ────────────────────────────────────────────────────────
    word_count = len(content_html.split()) if content_html else 0

    # ── Preview mode — return early with clean article view ──────────────────
    if mode == "preview":
        return ui.Stack(children=[
            header,
            meta,
            ui.Divider(),
            ui.Html(
                content=_article_html(
                    title or kw,
                    content_html or "<p><em>No content yet — run AI Write.</em></p>",
                ),
                theme="light",
            ),
        ])

    # ── Edit mode continues below ─────────────────────────────────────────────
    step3_title = f"Step 3 — Edit & Save{f'  ·  {word_count:,} words' if word_count else ''}"
    if show_editor:
        step3 = ui.Section(title=step3_title, children=[
            ui.Form(
                action="save_draft",
                submit_label="Save",
                children=[
                    ui.Input(param_name="title", value=title, placeholder="Article title (H1)"),
                    ui.RichEditor(
                        param_name="content",
                        content=content_html,
                        placeholder="Run AI Write above, or start typing here...",
                    ),
                ],
            ),
            ui.Stack(direction="h", children=[
                ui.Button(label="Hide editor", on_click=ui.Call("__panel__editor", active_view="editor", show_editor="0", note_id="board"), size="sm", variant="ghost"),
            ]),
        ])
    else:
        # Compact inline — no Section to avoid empty black void
        edit_row_children = []
        if has_content:
            edit_row_children.append(ui.Text(content=f"{word_count:,} words ready.", variant="caption"))
        edit_row_children.append(
            ui.Button(label="✏ Edit article", on_click=ui.Call("__panel__editor", active_view="editor", show_editor="1", note_id="board"), size="sm"),
        )
        step3 = ui.Stack(children=[
            ui.Text(content=step3_title, variant="caption"),
            ui.Stack(direction="h", gap=8, children=edit_row_children),
        ])

    # ── Step 4: Publish ───────────────────────────────────────────────────────
    seo_done = bool(item.get("meta_description") or item.get("excerpt"))
    wp_admin_link = f"{wp_base_url}/wp-admin/post.php?post={wp_id}&action=edit" if wp_base_url and wp_id else ""

    if wp_id:
        link_parts = []
        if wp_url:
            link_parts.append(f'<a href="{wp_url}" target="_blank" style="font-size:12px;color:#0073aa;text-decoration:none;">↗ View post</a>')
        if wp_admin_link:
            link_parts.append(f'<a href="{wp_admin_link}" target="_blank" style="font-size:12px;color:#555;text-decoration:none;">✏ Edit in WP Admin</a>')

        publish_section = ui.Section(
            title=f"Step 4 — Published (WP #{wp_id})",
            children=[
                ui.Stack(children=[
                    ui.Badge(label=f"WP #{wp_id}", color="green"),
                    ui.Badge(
                        label="Rank Math ✓" if seo_done else "Rank Math not set",
                        color="green" if seo_done else "orange",
                    ),
                ], direction="h", gap=8),
                *([ ui.Html(content=f'<div style="display:flex;gap:16px;margin:4px 0;">{"  ".join(link_parts)}</div>') ] if link_parts else []),
                ui.Stack(children=[
                    ui.Form(action="publish_wp_draft",   submit_label="Update WP Post",   children=[]),
                    ui.Form(action="publish_wp_publish", submit_label="Set as Published", children=[]),
                ], direction="h", gap=8),
                ui.Divider(),
                ui.Header(text="SEO Meta (Rank Math)", level=5),
                ui.Text(content="Sets focus + secondary keywords, meta description, excerpt. All auto-generated if left empty.", variant="caption"),
                ui.Form(
                    action="set_wp_seo",
                    submit_label="Set SEO Meta",
                    children=[
                        ui.Input(param_name="focus_keyword",    value=focus_kw,   placeholder=f"Focus keyword (default: {kw})"),
                        ui.Input(param_name="meta_description", value=meta_desc,  placeholder="Meta description (leave empty — AI generates)"),
                    ],
                ),
            ],
            collapsible=True,
            )
    else:
        publish_section = ui.Section(
            title="Step 4 — Publish to WordPress",
            children=[
                ui.Text(
                    content="Publishes as draft — you can review in WP before going live.",
                    variant="caption",
                ),
                ui.Stack(children=[
                    ui.Form(action="publish_wp_draft",   submit_label="→ Save as WP Draft", children=[]),
                    ui.Form(action="publish_wp_publish", submit_label="→ Publish Now",      children=[]),
                ], direction="h", gap=8),
            ],
        )

    status_section = ui.Section(
        title=f"Status: {status}",
        collapsible=True,
        children=[
            ui.Text(content="Statuses update automatically. Use only if you need to override.", variant="caption"),
            ui.Form(
                action="update_status",
                submit_label="Set status",
                children=[
                    ui.Select(param_name="status", placeholder=f"Current: {status}", options=[
                        {"value": "idea",      "label": "Idea"},
                        {"value": "writing",   "label": "Writing"},
                        {"value": "review",    "label": "Review"},
                        {"value": "published", "label": "Published"},
                    ]),
                ],
            ),
        ],
    )

    # ── GSC stats section ─────────────────────────────────────────────────────
    gsc_children = []
    if gsc_data and gsc_data.get("stats") and gsc_data["stats"].get("clicks", 0) >= 0:
        stats = gsc_data["stats"]
        kws = (gsc_data.get("keywords") or [])[:8]
        gsc_children = [
            ui.Stack(direction="h", gap=16, children=[
                ui.Stat(label="Clicks (90d)",  value=str(stats.get("clicks", 0)),        color="blue",   icon="MousePointerClick"),
                ui.Stat(label="Impressions",   value=f"{stats.get('impressions', 0):,}", color="gray",   icon="Eye"),
                ui.Stat(label="CTR",           value=f"{stats.get('ctr', 0):.1f}%",      color="green",  icon="TrendingUp"),
                ui.Stat(label="Avg Position",  value=str(stats.get("position", "—")),    color="purple", icon="Hash"),
            ]),
            *([ ui.DataTable(
                columns=[
                    ui.DataColumn(key="query",    label="Query",    width="50%"),
                    ui.DataColumn(key="clicks",   label="Clicks",   width="15%"),
                    ui.DataColumn(key="impr",     label="Impr.",    width="15%"),
                    ui.DataColumn(key="position", label="Position", width="20%"),
                ],
                rows=[{"query": k.get("query",""), "clicks": str(k.get("clicks",0)),
                       "impr": str(k.get("impressions",0)), "position": str(k.get("position",0))}
                      for k in kws],
            ) ] if kws else [ ui.Text(content="No queries data yet.", variant="caption") ]),
        ]
    elif wp_url:
        gsc_children = [ ui.Text(content="Connect GSC in Settings to see organic clicks, impressions, and top queries for this page.", variant="caption") ]

    gsc_section = ui.Section(title="📊 Google Search Console", collapsible=True, children=gsc_children) if wp_url else None

    return ui.Stack(children=[
        header,
        meta,
        ui.Divider(),
        step1,
        step2,
        ui.Divider(),
        step3,
        ui.Divider(),
        publish_section,
        ui.Divider(),
        status_section,
        *([ ui.Divider(), gsc_section ] if gsc_section else []),
    ])

