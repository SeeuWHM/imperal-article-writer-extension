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

NAV_COL = "article_writer_nav_state"
STATUS_ORDER = ["idea", "writing", "review", "published"]
STATUS_COLOR = {"idea": "gray", "writing": "blue", "review": "yellow", "published": "green"}


async def _load_nav(ctx) -> dict:
    try:
        page = await ctx.store.query(NAV_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs and isinstance(getattr(docs[0], "data", None), dict):
            return docs[0].data
    except Exception:
        pass
    return {}


async def _save_nav(ctx, values: dict) -> None:
    try:
        page = await ctx.store.query(NAV_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs:
            await ctx.store.update(NAV_COL, docs[0].id, values)
        else:
            await ctx.store.create(NAV_COL, values)
    except Exception:
        pass  # nav-state persistence is a convenience, never load-bearing


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

    new_article_form = ui.Form(
        action="create_article",
        submit_label="+ New article",
        defaults={"project_id": project_id},
        children=[
            ui.Input(param_name="title", placeholder="Title (optional)"),
            ui.Input(param_name="target_keyword", placeholder="Target keyword (optional)"),
        ],
    )

    return ui.Stack(children=[
        ui.Grid(columns=len(STATUS_ORDER), gap=3, children=columns),
        ui.Divider(),
        new_article_form,
    ])


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

    header = ui.Stack(children=[
        _back_button(project_id),
        ui.Header(text=data.get("title") or data.get("target_keyword") or "(untitled)", level=4),
        ui.Stack(direction="h", gap=2, children=[
            ui.Badge(label=data.get("status", "idea"), color=STATUS_COLOR.get(data.get("status", "idea"), "gray")),
            ui.Badge(label=f"{data.get('word_count', 0)} words", color="gray"),
            *([ui.Badge(label=f, color="yellow") for f in flags]),
        ]),
    ], gap=2)

    status_form = ui.Form(
        action="update_article_status", submit_label="Update status",
        defaults={"article_id": article_id},
        children=[
            ui.Select(param_name="status", value=data.get("status", "idea"), options=[
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
        patch_form = ui.Form(
            action="patch_article", submit_label="Patch with AI",
            defaults={"article_id": article_id},
            children=[
                ui.Input(param_name="instruction", placeholder="e.g. rewrite the intro to be punchier"),
                ui.Input(param_name="section_hint", placeholder="Optional heading/keyword hint"),
            ],
        )
        body = ui.Stack(children=[
            patch_form,
            ui.Divider(),
            _article_editor(article_id, sections),
        ])

    delete_btn = ui.Button(label="Delete article", variant="danger", size="sm",
                            on_click=ui.Call("delete_article", article_id=article_id))

    return ui.Stack(children=[header, status_form, ui.Divider(), body, ui.Divider(), delete_btn])


@ext.panel("workspace", slot="center", title="Article Writer", icon="FileText",
           refresh="on_event:article-writer.article.created,article-writer.article.status_changed,"
                   "article-writer.article.section_saved,article-writer.article.patched,"
                   "article-writer.article.deleted,article-writer.article.generation_started,"
                   "article-writer.project.deleted")
async def workspace_panel(ctx, view: str = "", project_id: str = "", article_id: str = ""):
    nav = await _load_nav(ctx)
    view = view or nav.get("view") or "articles"
    project_id = project_id or nav.get("project_id") or ""
    article_id = article_id or nav.get("article_id") or ""

    await _save_nav(ctx, {"view": view, "project_id": project_id, "article_id": article_id})

    if view == "article":
        return await _render_article_view(ctx, project_id, article_id)
    return await _render_articles_view(ctx, project_id)
