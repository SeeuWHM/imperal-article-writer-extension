"""Tiny shared nav-state doc — which project/article/view is currently open.

Written by panels_workspace.py on every render (so the center panel survives
a plain reload with no kwargs) and read by panels_side.py too, so the
sidebar knows which project is "open" right now without the two panels
needing any direct reference to each other. Holds only IDs/view name, never
article content.
"""
from __future__ import annotations

NAV_COL = "article_writer_nav_state"


async def load_nav(ctx) -> dict:
    try:
        page = await ctx.store.query(NAV_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs and isinstance(getattr(docs[0], "data", None), dict):
            return docs[0].data
    except Exception:
        pass
    return {}


async def save_nav(ctx, values: dict) -> None:
    try:
        page = await ctx.store.query(NAV_COL, limit=1)
        docs = getattr(page, "data", None) or []
        if docs:
            await ctx.store.update(NAV_COL, docs[0].id, values)
        else:
            await ctx.store.create(NAV_COL, values)
    except Exception:
        pass  # nav-state persistence is a convenience, never load-bearing
