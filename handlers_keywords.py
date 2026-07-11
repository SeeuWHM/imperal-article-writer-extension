"""SE Ranking tracked keyword management — add, remove, list."""
from imperal_sdk import ActionResult, ui
from imperal_sdk.types import ActionResult  # noqa: F811

from wpb_app import chat
from api_client import ser_add_keyword, ser_remove_keyword, ser_list_site_keywords
from params import EmptyParams
from response_models import TrackedKeywordsResponse

from pydantic import BaseModel, Field


class AddTrackedKeywordParams(BaseModel):
    keyword: str = Field(..., description="Keyword to start tracking in SE Ranking")
    landing_url: str = Field("", description="Landing page URL for this keyword (optional)")


class RemoveTrackedKeywordParams(BaseModel):
    keyword_id: str = Field("", description="SE Ranking keyword ID to remove (from list_tracked_keywords)")
    keyword: str = Field("", description="Keyword name to remove — system will find ID automatically")


@chat.function(
    "add_tracked_keyword",
    description=(
        "Add a keyword to SE Ranking position tracking. "
        "Use when user wants to track a new keyword — "
        "'добавь в трекинг', 'начать отслеживать кейворд', 'track this keyword', "
        "'хочу отслеживать позицию по слову X', 'add to SE Ranking', "
        "'мониторить позицию', 'add keyword tracking for X'."
    ),
    action_type="write",
    chain_callable=True,
    effects=["create:keyword"],
    event="seo.nav.changed",
)
async def add_tracked_keyword(ctx, params: AddTrackedKeywordParams) -> ActionResult:
    """Add keyword to SE Ranking position tracking."""
    result = await ser_add_keyword(ctx, params.keyword, params.landing_url)
    if "error" in result:
        return ActionResult.error(error=result["error"])
    added = result.get("response", {}).get("added", 0)
    kw_id = (result.get("response", {}).get("ids") or [None])[0]
    return ActionResult.success(
        data={"keyword": params.keyword, "id": kw_id, "added": added},
        summary=f"Added '{params.keyword}' to SE Ranking tracking. ID: {kw_id}\nPositions will update in the next daily check.",
    )


@chat.function(
    "remove_tracked_keyword",
    description=(
        "Remove a keyword from SE Ranking position tracking. "
        "Use when user says: stop tracking keyword, remove keyword from SE Ranking, "
        "удали кейворд из трекинга, убери ключевое слово из SE Ranking, "
        "перестань отслеживать X."
    ),
    action_type="write",
    chain_callable=True,
    effects=["delete:keyword"],
    event="seo.nav.changed",
)
async def remove_tracked_keyword(ctx, params: RemoveTrackedKeywordParams) -> ActionResult:
    """Remove keyword from SE Ranking tracking by name or ID."""
    keyword_id = params.keyword_id

    if not keyword_id and params.keyword:
        data = await ser_list_site_keywords(ctx)
        if "error" in data:
            return ActionResult.error(error=data["error"])
        all_kws = data.get("keywords", [])
        match = next(
            (k for k in all_kws if k.get("name", "").lower() == params.keyword.lower()),
            None,
        )
        if not match:
            return ActionResult.error(
                error=f"Keyword '{params.keyword}' not found in SE Ranking tracking. Check with list_tracked_keywords."
            )
        keyword_id = str(match.get("id", ""))

    if not keyword_id:
        return ActionResult.error(error="Provide keyword name or ID.")

    result = await ser_remove_keyword(ctx, keyword_id)
    if "error" in result:
        return ActionResult.error(error=result["error"])

    return ActionResult.success(
        data={"keyword_id": keyword_id},
        summary=f"Removed keyword ID {keyword_id} from SE Ranking tracking.",
    )


@chat.function(
    "list_tracked_keywords",
    description=(
        "List all keywords tracked in SE Ranking with IDs and positions. "
        "Use when user wants to see tracked keywords — "
        "'какие ключевые слова я отслеживаю', 'список трекинга', "
        "'сколько кейвордов в трекинге', 'show tracked keywords', "
        "'what am I tracking in SE Ranking', 'покажи все мои ключевые слова'."
    ),
    action_type="read",
    data_model=TrackedKeywordsResponse,
)
async def list_tracked_keywords(ctx, params: EmptyParams) -> ActionResult:
    """List all keywords tracked in SE Ranking with IDs."""
    data = await ser_list_site_keywords(ctx)
    if "error" in data:
        return ActionResult.error(error=data["error"])

    kws = data.get("keywords", [])
    if not kws:
        return ActionResult.success(data={"keywords": [], "count": 0},
                                    summary="No keywords tracked in SE Ranking yet.")

    rows = [
        {
            "id":      str(k.get("id", "—")),
            "keyword": k.get("name", "—"),
            "url":     (k.get("landing_url") or "")[:40] or "—",
            "group":   k.get("group_name", "—"),
        }
        for k in kws[:100]
    ]

    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="id",      label="ID",      width="15%"),
            ui.DataColumn(key="keyword", label="Keyword", width="45%"),
            ui.DataColumn(key="url",     label="URL",     width="25%"),
            ui.DataColumn(key="group",   label="Group",   width="15%"),
        ],
        rows=rows,
    )

    return ActionResult.success(
        data={"keywords": kws, "count": len(kws)},
        summary=f"{len(kws)} keywords tracked in SE Ranking.\nUse keyword ID with remove_tracked_keyword to stop tracking.",
        ui=table,
    )
