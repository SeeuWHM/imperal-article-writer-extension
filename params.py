"""Pydantic parameter models for all chat functions."""
from typing import Optional
from pydantic import BaseModel, Field


class CreateContentParams(BaseModel):
    keyword: str = Field(..., description="Target keyword for this content")
    type: str = Field("blog", description="'blog' or 'newsletter'")
    title: str = Field("", description="Content title (optional, AI can generate)")
    volume: int = Field(0, description="Monthly search volume from SE Ranking")
    difficulty: int = Field(0, description="Keyword difficulty 0-100")


class SaveDraftParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    title: str = Field("", description="Article or newsletter title")
    content: str = Field("", description="HTML content from the editor")
    subject: str = Field("", description="Email subject line (newsletter only)")


class UpdateStatusParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    status: str = Field(..., description="New status: idea|writing|review|published")


class DeleteContentParams(BaseModel):
    content_id: str = Field(..., description="Content item ID to delete")


class OpenEditorParams(BaseModel):
    content_id: str = Field(..., description="Content item ID to open in editor")


class SetEditorModeParams(BaseModel):
    mode: str = Field(..., description="'edit' or 'preview'")


class AiBriefParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    extra: str = Field("", description="Additional context or instructions for the AI")


class SaveBriefParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    brief_text: str = Field("", description="Brief content to save")


class AiWriteParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    section: str = Field("full", description="'full' or 'improve'")
    article_type: str = Field("", description="blog | comparison | tutorial | pillar | news | review — overrides item type")


class ImproveArticleParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    instruction: str = Field("", description="Optional specific improvement instruction")


class FetchKeywordsParams(BaseModel):
    domain: str = Field("", description="Domain to analyse — leave empty to use domain from Settings")
    source: str = Field("", description="Regional database code, e.g. 'us', 'gb' — empty = use Settings")
    limit: int = Field(80, description="Number of keywords to return (max 100)")
    min_volume: int = Field(50, description="Minimum monthly search volume")
    max_difficulty: int = Field(70, description="Maximum keyword difficulty")


class FetchGapsParams(BaseModel):
    competitor: str = Field(..., description="Competitor domain to compare against")
    source: str = Field("us", description="Regional database code")
    limit: int = Field(30, description="Number of gap keywords to return")


class PublishWpParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    keyword_hint: str = Field("", description="Keyword or title of the article — server resolves ID automatically")
    status: str = Field("draft", description="WP post status: 'draft' or 'publish'")


class SetWpSeoParams(BaseModel):
    content_id: str = Field("", description="Content item ID — leave empty to use currently open item")
    keyword_hint: str = Field("", description="Keyword or title of the article to update — server resolves ID automatically")
    meta_description: str = Field("", description="SEO meta description (120-155 chars) — leave empty to auto-generate")
    focus_keyword: str = Field("", description="Rank Math focus keyword — leave empty to use item's keyword")


class EmptyParams(BaseModel):
    pass


class FetchRankingsParams(BaseModel):
    pass


class ListProjectsParams(BaseModel):
    pass


class UploadDocParams(BaseModel):
    files: Optional[list] = Field(None, description="Base64-encoded files from FileUpload component")


class DeleteDocParams(BaseModel):
    doc_id: str = Field(..., description="Store ID of the doc to delete")


class GenerateNewsletterParams(BaseModel):
    content_id: str = Field("", description="Newsletter content item ID — leave empty to use currently open item")
    news_text: str = Field(..., description="The news, update, or topic to write the newsletter about")
    tone_note: str = Field("", description="Optional tone instruction, e.g. 'more urgent', 'focus on price'")


class BuildPlanParams(BaseModel):
    competitor: Optional[str] = Field("", description="Competitor domain for gap analysis — empty = use Settings")
    language: str = Field("en", description="Content language: 'en' or 'ru'")


class UIStateModel(BaseModel):
    active_view: str = "plan"
    selected_id: Optional[str] = None
    editor_mode: str = "edit"
    kw_results: list = Field(default_factory=list)
    rankings_results: list = Field(default_factory=list)
    show_editor: bool = False


class SaveSettingsParams(BaseModel):
    # Backend bridge / compat API
    backend_url: Optional[str] = None
    backend_api_key: Optional[str] = None
    # SE Ranking
    seranking_api_key: Optional[str] = None
    seranking_data_key: Optional[str] = None  # legacy alias accepted for migration/tests
    seranking_project_id: Optional[str] = None
    seranking_project_key: Optional[str] = None  # legacy alias accepted for migration/tests
    seranking_domain: Optional[str] = None
    seranking_source: Optional[str] = None
    seranking_competitor: Optional[str] = None
    # WordPress
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_app_password: Optional[str] = None
    wp_author_id: Optional[int] = None
    # Matomo analytics
    matomo_url: Optional[str] = None
    matomo_token: Optional[str] = None
    matomo_site_id: Optional[int] = None
    # Brand identity
    company_name: Optional[str] = None
    brand_description: Optional[str] = None
    brand_voice: Optional[str] = None
    newsletter_cta: Optional[str] = None
    site_url: Optional[str] = None
    blog_url: Optional[str] = None
    tg_url: Optional[str] = None
    community_url: Optional[str] = None


class SetupBlogStyleParams(BaseModel):
    blog_url: Optional[str] = None


class PatchArticleParams(BaseModel):
    instruction: str
    content_id: str = Field('', description='Content item ID — leave empty to use currently open item')
    keyword_hint: str = Field('', description='Keyword or title to find the article if no content_id or open article')


class ListWpPostsParams(BaseModel):
    status: Optional[str] = Field('any', description='Post status: any, publish, draft')
    per_page: Optional[int] = Field(20, description='Number of posts to return (max 50)')


class ImportFromWpParams(BaseModel):
    post_id: Optional[int] = Field(None, description='WordPress post ID to import')
    keyword_hint: Optional[str] = Field(None, description='Post title or keyword to search for in WordPress')
    instruction: Optional[str] = Field(None, description='If provided, immediately edit the post after importing (e.g. rewrite intro, add section)')


class UnpublishWpParams(BaseModel):
    content_id: str = Field('', description='Content item ID — leave empty to use currently open item')
    keyword_hint: str = Field('', description='Post title/keyword to find if no content_id')


class GetArticleLinkParams(BaseModel):
    title_or_keyword: str = Field(..., description='Title or keyword to search for in WordPress posts')


class RewriteArticleParams(BaseModel):
    content_id: str = Field('', description='Content item ID — leave empty to use currently open item')
    instruction: str = Field('', description='Optional focus for the rewrite (e.g. "more conversational tone", "comparison style")')


class AddKeywordsParams(BaseModel):
    keywords: str = Field(..., description='Comma-separated keywords to add to the article and Rank Math')
    content_id: str = Field('', description='Content item ID — leave empty to use currently open item')


class CheckSeoMetaParams(BaseModel):
    content_id: str = Field('', description='Content item ID — leave empty to use currently open item')
    keyword_hint: str = Field('', description='Post title/keyword to find if no content_id')
