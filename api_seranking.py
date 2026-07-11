"""SE Ranking API client.

Two separate APIs with separate keys:
- Data API  : https://api.seranking.com/v1  — keyword research, domain analysis
- Project API: https://api4.seranking.com   — rank tracking for a configured project
"""
from __future__ import annotations

DATA_BASE = "https://api.seranking.com/v1"
PROJ_BASE = "https://api4.seranking.com"


def _data_headers(key: str) -> dict:
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


def _proj_headers(key: str) -> dict:
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


# ── Data API ──────────────────────────────────────────────────────────────────

async def domain_keywords(
    ctx,
    key: str,
    domain: str,
    source: str = "us",
    limit: int = 50,
    min_volume: int = 100,
    max_difficulty: int = 60,
) -> list[dict]:
    """Organic keywords a domain ranks for, with positions and metrics."""
    params = {
        "source": source,
        "domain": domain,
        "type": "organic",
        "order_field": "traffic",
        "limit": min(limit, 100),
        "filter[volume][from]": min_volume,
        "filter[difficulty][to]": max_difficulty,
    }
    resp = await ctx.http.get(
        f"{DATA_BASE}/domain/keywords",
        headers=_data_headers(key),
        params=params,
    )
    return _parse_list(resp.json() if resp.ok else [])


async def keyword_gaps(
    ctx,
    key: str,
    domain: str,
    competitor: str,
    source: str = "us",
    limit: int = 30,
) -> list[dict]:
    """Keywords the competitor ranks for but our domain does not (diff=1)."""
    params = {
        "source": source,
        "domain": domain,
        "compared_domain": competitor,
        "diff": 1,
        "type": "organic",
        "order_field": "volume",
        "limit": min(limit, 100),
    }
    resp = await ctx.http.get(
        f"{DATA_BASE}/domain/keywords/comparison",
        headers=_data_headers(key),
        params=params,
    )
    return _parse_list(resp.json() if resp.ok else [])


async def account_subscription(ctx, key: str) -> dict:
    """Verify the Data API key and return subscription info."""
    resp = await ctx.http.get(
        f"{DATA_BASE}/account/subscription",
        headers=_data_headers(key),
    )
    return _parse_dict(resp.json() if resp.ok else {})


# ── Project API ───────────────────────────────────────────────────────────────

async def list_projects(ctx, key: str) -> list[dict]:
    """List all rank-tracking projects in the account."""
    resp = await ctx.http.get(
        f"{PROJ_BASE}/project/list-projects",
        headers=_proj_headers(key),
    )
    return _parse_list(resp.json() if resp.ok else [])


async def project_rankings(ctx, key: str, project_id: str) -> list[dict]:
    """Keyword rankings for a specific project."""
    resp = await ctx.http.get(
        f"{PROJ_BASE}/project/keyword-statistics",
        headers=_proj_headers(key),
        params={"project_id": project_id},
    )
    return _parse_list(resp.json() if resp.ok else [])


async def project_summary(ctx, key: str, project_id: str) -> dict:
    """Summary stats for a project (visibility, avg. position, etc.)."""
    resp = await ctx.http.get(
        f"{PROJ_BASE}/project/summary-statistics",
        headers=_proj_headers(key),
        params={"project_id": project_id},
    )
    return _parse_dict(resp.json() if resp.ok else {})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_list(resp) -> list[dict]:
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("data", "keywords", "items", "results"):
            if isinstance(resp.get(key), list):
                return resp[key]
    return []


def _parse_dict(resp) -> dict:
    if isinstance(resp, dict):
        return resp
    return {}
