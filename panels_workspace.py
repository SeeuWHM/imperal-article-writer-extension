"""Center workspace panel — article board + article editor.

Reads/edits full article bodies directly via plain server-side Python
(call_backend) — no LLM completion is ever involved in rendering this
panel or in submitting its Save-section form, so it costs zero LLM tokens
regardless of how many articles or how long they are. This is the ONLY
place full article bodies are ever displayed — chat functions never
receive them (see response_models.ArticleSummary's docstring).

Routing: `__panel__workspace` accepts (view, project_id, article_id) as
plain kwargs (SDK panel mechanism — see imperal_sdk.extension.Extension.panel).
Buttons/list items pass them via ui.Call("__panel__workspace", **kwargs). A
tiny nav-state doc in ctx.store remembers the last position across a plain
reload (no kwargs) — it holds only IDs/view name, never article content.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from api_client import call_backend
from richtext import sections_to_html
from navstate import load_nav, save_nav

STATUS_ORDER = ["idea", "writing", "review", "published"]
STATUS_COLOR = {"idea": "gray", "writing": "blue", "review": "yellow", "published": "green"}


def _back_button(project_id: str) -> ui.UINode:
    return ui.Button(label="← Back to articles", variant="ghost", size="sm",
                      on_click=ui.Call("__panel__workspace", view="articles", project_id=project_id))


async def _render_articles_view(ctx, project_id: str) -> ui.UINode:
    if not project_id:
        return ui.Empty(message="Pick a project on the left, or create one, to see its articles.")

    data = await call_backend(ctx, "GET", "/v1/articles", params={"project_id": project_id, "limit": 100, "offset": 0})
    if "error" in data:
        return ui.Alert(message=data["error"], type="error")
    articles = data.get("data") if isinstance(data.get("data"), list) else []
    articles = articles or []

    by_status: dict[str, list] = {s: [] for s in STATUS_ORDER}
    for a in articles:
        by_status.setdefault(a.get("status", "idea"), []).append(a)

    columns = []
    for status in STATUS_ORDER:
        items = by_status.get(status, [])
        columns.append(ui.Column(gap=2, children=[
            ui.Header(text=f"{status.capitalize()} · {len(items)}", level=6),
            *([
                ui.List(items=[
                    ui.ListItem(
                        id=a["id"], title=a.get("title") or a.get("target_keyword") or "(untitled)",
                        subtitle=f"{a.get('word_count', 0)} words",
                        badge=ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
                        on_click=ui.Call("__panel__workspace", view="article", project_id=project_id, article_id=a["id"]),
                    )
                    for a in items
                ]),
            ] if items else [ui.Text(content="—", variant="caption")]),
        ]))

    # No "+ New article" form here — Webbee creates articles via chat
    # (create_article); this panel's job is navigation + reading/editing,
    # not duplicating actions Webbee already owns.
    return ui.Grid(columns=len(STATUS_ORDER), gap=3, children=columns)


def _article_editor(article_id: str, sections: list[dict]) -> ui.UINode:
    """One seamless editable document — headings are real <h2>s inside the
    same RichEditor, not separate boxes. Saving splits it back into sections
    at heading boundaries (richtext.html_to_sections), so adding/removing/
    reordering a heading here is how sections get added/removed/reordered."""
    return ui.Form(
        action="save_full_article",
        submit_label="Save article",
        defaults={"article_id": article_id},
        children=[
            ui.RichEditor(param_name="content_html", content=sections_to_html(sections)),
        ],
    )


async def _render_article_view(ctx, project_id: str, article_id: str) -> ui.UINode:
    if not article_id:
        return ui.Empty(message="No article selected.")

    data = await call_backend(ctx, "GET", f"/v1/articles/{article_id}")
    if "error" in data:
        return ui.Stack(children=[_back_button(project_id), ui.Alert(message=data["error"], type="error")])

    project_id = project_id or data.get("project_id", "")
    seo_score = data.get("seo_score") or {}
    flags = seo_score.get("flags") or []
    sections = data.get("sections") or []
    status = data.get("status", "idea")

    delete_btn = ui.Button(label="Delete article", icon="Trash2", variant="danger", size="sm",
                           on_click=ui.Call("delete_article", article_id=article_id))

    # Top action bar: back on the left, destructive delete pinned to the far
    # right. A horizontal Stack keeps the ghost "Back" button at its content
    # width (a lone Button in a vertical Stack stretches full-width) and keeps
    # delete visually separated from it so it can't be misclicked.
    top_bar = ui.Stack(direction="h", gap=2, justify="between", align="center", wrap=True, children=[
        _back_button(project_id), delete_btn,
    ])

    badges = ui.Stack(direction="h", gap=2, wrap=True, children=[
        ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
        ui.Badge(label=f"{data.get('word_count', 0)} words", color="gray"),
        *([ui.Badge(label=f, color="yellow") for f in flags]),
    ])

    # Status control is its own full-width row (NOT nested inside a horizontal
    # flex row) — a ui.Form as a flex child breaks the layout flow and made the
    # whole header overlap. This is the same flat structure mail-client's
    # email-viewer panel uses.
    status_form = ui.Form(
        action="update_article_status", submit_label="Update status",
        defaults={"article_id": article_id},
        children=[
            ui.Select(param_name="status", value=status, options=[
                {"value": s, "label": s.capitalize()} for s in STATUS_ORDER
            ]),
        ],
    )

    if not sections:
        body = ui.Form(
            action="generate_article", submit_label="Generate first draft",
            defaults={"article_id": article_id},
            children=[
                ui.TextArea(param_name="brief", placeholder="What should this article cover?", rows=4),
                ui.Input(param_name="target_keyword", value=data.get("target_keyword") or "",
                         placeholder="Target keyword"),
                ui.TagInput(param_name="source_snippets",
                            placeholder="Real facts/data to ground the article in (optional)"),
            ],
        )
    else:
        # No "Patch with AI" form — that's Webbee's job via chat
        # (patch_article); this panel edits directly, it doesn't duplicate
        # Webbee's own AI-writing actions.
        body = _article_editor(article_id, sections)

    # Flat vertical document: action bar → title → badges → status control →
    # divider → body. No nested horizontal flex holding a Form (that was what
    # made the header elements pile on top of each other). className mirrors
    # mail-client's viewer so content isn't flush against the panel edge.
    return ui.Stack(gap=3, className="px-4 pb-4", children=[
        top_bar,
        ui.Header(text=data.get("title") or data.get("target_keyword") or "(untitled)", level=4),
        badges,
        status_form,
        ui.Divider(),
        body,
    ])


@ext.panel("workspace", slot="center", title="Article Writer", icon="FileText",
           refresh="on_event:article-writer.article.created,article-writer.article.status_changed,"
                   "article-writer.article.section_saved,article-writer.article.patched,"
                   "article-writer.article.deleted,article-writer.article.generation_started,"
                   "article-writer.project.deleted")
async def workspace_panel(ctx, view: str = "", project_id: str = "", article_id: str = ""):
    nav = await load_nav(ctx)
    view = view or nav.get("view") or "articles"
    project_id = project_id or nav.get("project_id") or ""
    article_id = article_id or nav.get("article_id") or ""

    await save_nav(ctx, {"view": view, "project_id": project_id, "article_id": article_id})

    if view == "article":
        return await _render_article_view(ctx, project_id, article_id)
    return await _render_articles_view(ctx, project_id)
