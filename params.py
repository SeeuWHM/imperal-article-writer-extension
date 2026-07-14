"""Pydantic param models for Article Writer chat functions.

Mirrors the backend's own request schemas exactly (see
article-writer-backend/service/apps/{projects,articles}/schemas.py) — this
extension is a thin, faithful client, not a second source of truth for
validation rules.
"""
# No `from __future__ import annotations` — chat.function's param validator
# needs real runtime type annotations (see se-ranking-connector/handlers.py
# for the same convention/reasoning).

from typing import List, Optional
from pydantic import BaseModel, Field


class CreateProjectParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name, e.g. the site's name")
    site_url: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    keywords: List[str] = Field(default_factory=list, description="Target keywords for this project")
    useful_links: List[str] = Field(default_factory=list)
    social_links: List[str] = Field(default_factory=list)
    brand_voice: Optional[str] = Field(default=None, max_length=5000, description="How this brand writes/sounds")


class UpdateProjectContextParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    name: Optional[str] = Field(default=None, max_length=255)
    site_url: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    keywords: Optional[List[str]] = Field(default=None)
    useful_links: Optional[List[str]] = Field(default=None)
    social_links: Optional[List[str]] = Field(default=None)
    brand_voice: Optional[str] = Field(default=None, max_length=5000)


class ProjectIdParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")


class CreateArticleParams(BaseModel):
    project_id: str = Field(..., description="Project this article belongs to")
    title: Optional[str] = Field(default=None, max_length=500)
    target_keyword: Optional[str] = Field(default=None, max_length=255)


class ListArticlesParams(BaseModel):
    project_id: Optional[str] = Field(default=None, description="Filter by project")
    status: Optional[str] = Field(default=None, description="idea | writing | review | published")


class ArticleIdParams(BaseModel):
    article_id: str = Field(..., description="Article ID from list_articles")


class UpdateArticleStatusParams(BaseModel):
    article_id: str = Field(...)
    status: str = Field(..., description="idea | writing | review | published")


class UpdateArticleMetaParams(BaseModel):
    article_id: str = Field(...)
    title: Optional[str] = Field(default=None, max_length=500)
    meta_description: Optional[str] = Field(
        default=None, max_length=320,
        description="SEO meta description — aim for 70-165 characters",
    )
    target_keyword: Optional[str] = Field(default=None, max_length=255)


class GenerateArticleParams(BaseModel):
    article_id: str = Field(...)
    brief: str = Field(..., min_length=1, max_length=10000, description="What the article should cover")
    target_keyword: Optional[str] = Field(default=None, max_length=255)
    source_snippets: List[str] = Field(
        default_factory=list,
        description="Real facts/data (from web search or other extensions) the article must be grounded in",
    )


class GenerationJobStatusParams(BaseModel):
    article_id: str = Field(...)
    job_id: str = Field(...)


class PatchArticleParams(BaseModel):
    article_id: str = Field(...)
    instruction: str = Field(..., min_length=1, max_length=2000, description="e.g. 'rewrite the paragraph about delivery'")
    section_hint: Optional[str] = Field(default=None, max_length=255, description="Heading or keyword to help locate the section")


class SaveArticleSectionParams(BaseModel):
    article_id: str = Field(...)
    order_index: int = Field(..., ge=0)
    heading: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = Field(default=None, max_length=200000)


class SaveFullArticleParams(BaseModel):
    """PANEL-ONLY: the whole merged document from the single-window editor —
    not something Webbee should ever construct from chat."""
    article_id: str = Field(...)
    content_html: str = Field(default="", max_length=400000)
