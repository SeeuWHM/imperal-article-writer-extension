"""Pydantic response models for Article Writer chat functions.

Every @chat.function(action_type="read") must declare a data_model so the
platform can validate return shapes (federal V23).

CRITICAL: ArticleSummary has no content/sections field, by design — mirrors
the backend's own apps/articles/schemas.py::ArticleSummary. list_articles
must never be able to carry a full article body, independent of what the
backend happens to send — see article-writer-backend/PLAN.md's token-economy
rule. Full bodies exist only in ArticleDetail, which this extension never
returns from a chat.function — only the panel (panels_workspace.py) reads it.

ArticleFullText is the ONE deliberate, explicit exception: cross-extension
handoffs (email the article, save it to a note, paste it elsewhere) are
things only Webbee can do — the panel can't call another extension's tools —
so Webbee needs a real, honest way to read the body when the user explicitly
asks for one of those, rather than inventing placeholder text because every
other function here structurally can't carry a body. Gated by description +
by being its own single-purpose function, not by being reachable from
list_articles/check_generation_status.
"""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


class ProjectRecord(BaseModel):
    id: str
    name: str = ""
    site_url: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    useful_links: List[str] = Field(default_factory=list)
    social_links: List[str] = Field(default_factory=list)
    brand_voice: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: List[ProjectRecord] = Field(default_factory=list)
    count: int = 0


class ArticleSummary(BaseModel):
    """Metadata only — DELIBERATELY no content/sections field. See module docstring."""

    id: str
    project_id: str
    title: Optional[str] = None
    status: str = "idea"
    target_keyword: Optional[str] = None
    meta_description: Optional[str] = None
    word_count: int = 0
    seo_flags: List[str] = Field(default_factory=list)
    model_used: Optional[str] = None


class ArticleListResponse(BaseModel):
    articles: List[ArticleSummary] = Field(default_factory=list)
    count: int = 0


class GenerationJobResponse(BaseModel):
    job_id: str
    article_id: str
    status: str = "queued"


class GenerationStatusResponse(BaseModel):
    job_id: str
    status: str
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
    error: Optional[str] = None


class PatchResult(BaseModel):
    """Never the full body — a short preview only."""

    section_id: str
    order_index: int
    heading: Optional[str] = None
    preview: str
    word_count: int = 0
    seo_flags: List[str] = Field(default_factory=list)


class DeletedResponse(BaseModel):
    deleted: bool = True


class ArticleFullText(BaseModel):
    """The one deliberate exception to 'never return body to chat' — see
    module docstring. Only export_article_text (handlers_articles.py)
    constructs this.

    `html` is real markup (<h2>, <strong>, <ul>...) — both Notes
    (content_text is "HTML content from Tiptap editor") and Mail's
    send/reply (is_html=true, added 2026-07-15) render it with formatting
    preserved, so there's no separate plain-text field to keep in sync."""

    id: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    html: str
