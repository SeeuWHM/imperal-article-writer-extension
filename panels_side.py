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


@ext.panel("sidebar", slot="left", title="Article Writer", icon="FileText",
           default_width=260,
           refresh="on_event:article-writer.project.created,article-writer.project.updated,article-writer.project.deleted")
async def sidebar_panel(ctx):
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
        body = [
            ui.Header(text="Article Writer", level=4),
            ui.List(items=[
                ui.ListItem(
                    id=p["id"], title=p.get("name") or "(untitled)",
                    subtitle=p.get("site_url") or "",
                    meta=f"{len(p.get('keywords') or [])} kw",
                    on_click=ui.Call("__panel__workspace", view="articles", project_id=p["id"]),
                )
                for p in projects
            ]),
        ]

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
