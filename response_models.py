from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class GenericPayloadResponse(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class NavStateResponse(BaseModel):
    section: str = "plan"
    filters: dict[str, Any] = Field(default_factory=dict)
    selected_id: str = ""
    editor_mode: str = "edit"
    show_editor: bool = False


class ArticleSummaryRecord(BaseModel):
    id: str = ""
    keyword: str = ""
    title: str = ""
    status: str = ""
    type: str = "blog"
    volume: Optional[int] = None
    difficulty: Optional[int] = None
    wp_post_id: Optional[int] = None
    wp_url: Optional[str] = None


class ArticleListResponse(BaseModel):
    items: list[ArticleSummaryRecord] = Field(default_factory=list)
    count: int = 0


class ArticleDetailResponse(BaseModel):
    item: dict[str, Any] = Field(default_factory=dict)


class QualityCheckResponse(BaseModel):
    content_id: str = ""
    quality_score: Optional[int] = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class DocRecord(BaseModel):
    id: str = ""
    name: str = ""
    size: Optional[int] = None
    uploaded_at: Optional[str] = None


class DocsListResponse(BaseModel):
    items: list[DocRecord] = Field(default_factory=list)
    count: int = 0


class TrackedKeywordRecord(BaseModel):
    keyword: str = ""
    position: Optional[float] = None
    url: Optional[str] = None
    volume: Optional[int] = None
    difficulty: Optional[int] = None


class TrackedKeywordsResponse(BaseModel):
    items: list[TrackedKeywordRecord] = Field(default_factory=list)
    count: int = 0


class SettingsResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class WPPostRecord(BaseModel):
    id: int | str
    title: str = ""
    status: str = ""
    url: Optional[str] = None


class WPPostsResponse(BaseModel):
    items: list[WPPostRecord] = Field(default_factory=list)
    count: int = 0


class LinkLookupResponse(BaseModel):
    url: str = ""


class KeywordResultRecord(BaseModel):
    keyword: str = ""
    volume: Optional[int] = None
    difficulty: Optional[int] = None
    cpc: Optional[float] = None
    position: Optional[float] = None
    url: Optional[str] = None


class KeywordResultsResponse(BaseModel):
    items: list[KeywordResultRecord] = Field(default_factory=list)
    count: int = 0


class GapResultRecord(BaseModel):
    keyword: str = ""
    volume: Optional[int] = None
    difficulty: Optional[int] = None
    position: Optional[float] = None
    competitor_position: Optional[float] = None
    cpc: Optional[float] = None


class GapResultsResponse(BaseModel):
    items: list[GapResultRecord] = Field(default_factory=list)
    count: int = 0


class RankingRecord(BaseModel):
    keyword: str = ""
    position: Optional[float] = None
    change: Optional[float] = None
    url: Optional[str] = None


class RankingsResponse(BaseModel):
    items: list[RankingRecord] = Field(default_factory=list)
    count: int = 0


class ProjectRecord(BaseModel):
    id: int | str
    name: str = ""
    domain: Optional[str] = None


class ProjectsResponse(BaseModel):
    items: list[ProjectRecord] = Field(default_factory=list)
    count: int = 0
