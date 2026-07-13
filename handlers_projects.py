"""Chat-function handlers: projects — the per-site context store.

Webbee fills a project's context in via web search + whatever other
extensions are installed (SE Ranking, GSC, Matomo, etc.) — this extension
only persists the assembled context; it has no idea those extensions exist.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend
from params import CreateProjectParams, UpdateProjectContextParams, ProjectIdParams
from response_models import ProjectRecord, ProjectListResponse, DeletedResponse
from pydantic import BaseModel


class _EmptyParams(BaseModel):
    """No input required."""


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


def _to_record(p: dict) -> ProjectRecord:
    return ProjectRecord(
        id=p.get("id", ""), name=p.get("name", ""), site_url=p.get("site_url"),
        description=p.get("description"), keywords=p.get("keywords") or [],
        useful_links=p.get("useful_links") or [], social_links=p.get("social_links") or [],
        brand_voice=p.get("brand_voice"),
    )


@chat.function(
    "create_project",
    description=(
        "Create a new project — a container for one site's context: keywords, brand voice, "
        "useful links, socials. Use for: создай проект, новый проект, add a new site/project, "
        "start tracking a new website."
    ),
    action_type="write",
    event="article-writer.project.created",
    effects=["create:project"],
    data_model=ProjectRecord,
)
async def fn_create_project(ctx, params: CreateProjectParams) -> ActionResult:
    """Create a new project context container for the caller's tenant."""
    data = await call_backend(ctx, "POST", "/v1/projects", json=params.model_dump(exclude_none=True))
    if "error" in data:
        return _err(data)
    record = _to_record(data)
    return ActionResult.success(
        data=record, summary=f'Created project "{record.name}".',
        refresh_panels=["sidebar"],
    )


@chat.function(
    "list_projects",
    description=(
        "List all projects (sites) — id, name, site url, keywords. Use for: покажи мои проекты, "
        "list my projects, what sites do I have."
    ),
    action_type="read",
    chain_callable=True,
    data_model=ProjectListResponse,
)
async def fn_list_projects(ctx, params: _EmptyParams) -> ActionResult:
    """Return every project owned by the caller's tenant."""
    data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    if "error" in data:
        return _err(data)
    raw = data.get("data") if isinstance(data.get("data"), list) else data.get("items") or []
    projects = [_to_record(p) for p in raw]
    result = ProjectListResponse(projects=projects, count=len(projects))
    rows = [
        {"name": p.name, "site_url": p.site_url or "", "keywords": ", ".join(p.keywords[:5])}
        for p in projects
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="name", label="Project", width="30%"),
            ui.DataColumn(key="site_url", label="Site", width="35%"),
            ui.DataColumn(key="keywords", label="Keywords", width="35%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No projects yet — create one first.")
    return ActionResult.success(data=result, summary=f"{len(projects)} project(s)", ui=ui_node)


@chat.function(
    "update_project_context",
    description=(
        "Update a project's context — any of: name, site url, description, keywords, useful "
        "links, social links, brand voice. Only send fields that changed. Use for: обнови "
        "проект, add keywords to project, update brand voice, add a useful link."
    ),
    action_type="write",
    event="article-writer.project.updated",
    effects=["update:project"],
    data_model=ProjectRecord,
)
async def fn_update_project_context(ctx, params: UpdateProjectContextParams) -> ActionResult:
    """Patch one or more context fields on an existing project."""
    fields = params.model_dump(exclude_none=True, exclude={"project_id"})
    if not fields:
        return ActionResult.error(error="Nothing to update — provide at least one field.")
    data = await call_backend(ctx, "PATCH", f"/v1/projects/{params.project_id}/context", json=fields)
    if "error" in data:
        return _err(data)
    record = _to_record(data)
    return ActionResult.success(
        data=record, summary=f'Updated "{record.name}".', refresh_panels=["sidebar"],
    )


@chat.function(
    "delete_project",
    description=(
        "Permanently delete a project and ALL its articles. Use for: удали проект, delete "
        "this project, remove site."
    ),
    action_type="destructive",
    event="article-writer.project.deleted",
    effects=["delete:project"],
    data_model=DeletedResponse,
)
async def fn_delete_project(ctx, params: ProjectIdParams) -> ActionResult:
    """Delete a project and cascade-delete all of its articles."""
    data = await call_backend(ctx, "DELETE", f"/v1/projects/{params.project_id}")
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(), summary="Project deleted.", refresh_panels=["sidebar", "workspace"],
    )
