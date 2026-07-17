"""Left sidebar — project switcher + new-project form.

Full context (description/links/socials/brand voice) is filled in later via
chat (update_project_context) — Webbee assembles it with web search and
whatever other extensions are installed. This form only needs the minimum
to create the container: name, site, and a first pass at keywords.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from api_client import call_backend
from navstate import load_nav


def _active_project_detail(p: dict) -> ui.UINode:
    """Full context (keywords, description) — shown ONLY for the project
    currently open in the center panel. Every other project is just a
    compact clickable row (_project_row) — no point showing every project's
    keyword list when only one is actually being worked on."""
    keywords = p.get("keywords") or []
    children = [
        ui.Header(text=p.get("name") or "(untitled)", level=5),
    ]
    if p.get("site_url"):
        children.append(ui.Text(content=p["site_url"], variant="caption"))
    if p.get("description"):
        children.append(ui.Text(content=p["description"], variant="caption"))
    children.append(
        ui.Stack(direction="h", gap=1, children=[ui.Badge(label=k, color="blue") for k in keywords])
        if keywords else ui.Text(content="No keywords yet.", variant="caption")
    )
    return ui.Stack(gap=1, children=children)


def _project_list_item(p: dict) -> ui.UINode:
    """One compact row for a project that ISN'T the one currently open.

    Routes through open_project (a real chat.function with
    refresh_panels=["sidebar", "workspace"]), NOT a raw
    ui.Call("__panel__workspace", ...) — a plain panel-to-panel Call only
    ever refreshes the ONE panel it targets, so the sidebar itself silently
    kept showing the previous project's expanded detail until a full page
    reload (live bug, 2026-07-18)."""
    return ui.ListItem(
        id=p["id"], title=p.get("name") or "(untitled)", subtitle=p.get("site_url") or "",
        on_click=ui.Call("open_project", project_id=p["id"]),
    )


@ext.panel("sidebar", slot="left", title="Article Writer", icon="FileText",
           default_width=260,
           refresh="on_event:article-writer.project.created,article-writer.project.updated,article-writer.project.deleted")
async def sidebar_panel(ctx):
    nav = await load_nav(ctx)
    active_project_id = nav.get("project_id") or ""

    data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    projects = data.get("data") if isinstance(data.get("data"), list) else []
    projects = projects or []

    if "error" in data and not projects:
        body = [
            ui.Header(text="Article Writer", level=4),
            ui.Alert(message=data["error"], type="error"),
        ]
    elif not projects:
        body = [
            ui.Header(text="Article Writer", level=4),
            ui.Text(content="No projects yet — create your first one below.", variant="caption"),
        ]
    else:
        active = next((p for p in projects if p["id"] == active_project_id), None)
        others = [p for p in projects if p["id"] != active_project_id]
        body = [ui.Header(text="Article Writer", level=4)]
        if active:
            body.append(_active_project_detail(active))
            if others:
                body.append(ui.Divider())
        if others:
            # ListItem must live inside a List — a bare ListItem as a direct
            # Stack child is what made the whole sidebar vanish after the
            # split-view change (this exact bug, live 2026-07-14).
            body.append(ui.List(items=[_project_list_item(p) for p in others]))

    new_project_form = ui.Form(
        action="create_project",
        submit_label="+ New project",
        children=[
            ui.Input(param_name="name", placeholder="Project name (e.g. site name)"),
            ui.Input(param_name="site_url", placeholder="Site URL (optional)"),
            ui.TagInput(param_name="keywords", placeholder="Target keywords (optional)"),
        ],
    )

    root = ui.Stack(children=[
        *body,
        ui.Divider(),
        new_project_form,
    ])
    # Claim the center slot on first load — without this, clicks routed to
    # __panel__workspace from here would open in "right" instead of "center".
    root.props["auto_action"] = ui.Call("__panel__workspace").to_dict()
    return root
