# Article Writer Extension — Full Documentation

**Version:** 1.5.3 | **Status (live, `mcp__imperal__get_app`):** `draft`, reject_reason "Does not meet quality standards"
**app_id:** `imperal-article-writer-extension` | **tool_name:** `article_writer`
**Git:** `github.com/SeeuWHM/imperal-article-writer-extension`
**Live manifest last updated:** 2026-07-12T21:35:23 — matches local HEAD (`254ac15`) exactly: version 1.5.3, 67 tools, `secrets: null` on both sides.

This document was written by reading every `.py` file in this repo directly, cross-checking
`imperal.json` against the source, and calling `mcp__imperal__get_app` for the live deployed
state. Nothing below is inferred from an old conversation/summary — where something was unclear
in the code it is marked "unclear" rather than guessed.

---

## What this actually is

A WordPress-focused SEO content studio: keyword research + rank tracking (SE Ranking), Google
Search Console reporting, AI article writing, and one-click WordPress publishing — all in one
extension, with its own kanban-style content plan (idea → writing → review → published).

It is **not** currently a thin "Webbee orchestrates everything" design — it has its own direct
SE Ranking, WordPress, and GSC integrations built in, plus one working cross-extension IPC call
into the separate Matomo Analytics Connector extension (see "Cross-extension integration" below).

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (63) or panel action
handlers_*.py
    ↓ HTTP (api_client._post/_get, Bearer token) → per-user `backend_url`
      "MOS" backend — content storage (/api/storage/content/*, /api/storage/docs/*),
      AI generation (/api/content/*), SE Ranking proxy (/api/seranking/*),
      GSC proxy (/api/gsc/*). Base URL + Bearer key are BOTH per-user ctx.store settings
      (backend_url / backend_api_key) — there is no shared/hardcoded backend constant
      like matomo-analytics-extension's SERVER_URL.
    ↓ WordPress REST API — called DIRECTLY from the extension (api_wordpress.py),
      NOT proxied through backend_url. Basic auth via Application Password.
    ↓ Matomo growing-pages/config — via ctx.extensions.call("analytics", ...) IPC
      into the separate Matomo Analytics Connector extension (see below).
```

I could not identify what actually runs behind `backend_url` (no api-server systemd service
matching "article-writer"/"content"/"mos" was checked in this pass — the base URL is a value
the *user* pastes into Settings, so it isn't a fixed, locatable service the way
`matomo-analytics-api` is). Treat `backend_url`/`backend_api_key` as "some external HTTP API the
user is expected to already have," not a WebHostMost-operated service I verified.

### Cross-extension integration (real, partially broken)

`skeleton.py::skeleton_refresh_wp_config` and `api_client.py::content_plan()` both call:
```python
await ctx.extensions.call("analytics", "matomo_config")
await ctx.extensions.call("analytics", "growing_pages", limit=20)
```
This is a genuine IPC call into the Matomo Analytics Connector extension (`tool_name="analytics"`)
— exactly the "Webbee/extensions call each other" pattern that was discussed as the target
architecture. **However**, as of this session's Matomo work, `matomo_config`'s IPC response no
longer includes `matomo_url` or `matomo_token` (that extension's `ipc_matomo_config` was
deliberately changed to stop leaking the raw token/URL — see `test_ipc_matomo_config_does_not_leak_token`
in `matomo-analytics-extension`). That means:
- `api_client.py:184-186` (`matomo_url = d.get("matomo_url", "")`, etc.) will always read empty
  strings now, even when Matomo *is* configured — the "fallback Matomo credentials forwarded to
  our own backend" path in `content_plan()` is silently dead.
- `skeleton.py:104` (`matomo_url = d.get("matomo_url", "")`) will always be `""`, so the skeleton
  instruction text reads "✓ connected at " with nothing after "at".
- `growing_pages` IPC (`ctx.extensions.call("analytics", "growing_pages", ...)`) is unaffected —
  that endpoint's contract didn't change — so the primary "find growing pages for content ideas"
  path still works.

This is a real, currently-live integration gap between the two extensions, not a hypothetical.

`params.py::SaveSettingsParams` also still declares `matomo_url` / `matomo_token` / `matomo_site_id`
fields — but `wpb_app.py::DEFAULT_SETTINGS` doesn't include them and nothing reads them back out of
`ctx.store` anywhere in the codebase. They're accepted by `save_settings` (would be written to
`ctx.store` if a caller ever passed them) but are otherwise dead — leftover from before the IPC
integration existed.

---

## File structure (verified against actual imports, not assumed)

```
article-writer-extension/
├── main.py                     — entry point; hot-reload module list; force-registers
│                                  params.py/api_client.py by absolute path (guards against a
│                                  same-named params.py in another installed extension's shared
│                                  Python env)
├── wpb_app.py                  — Extension + ChatExtension init, settings/UI-state/content
│                                  store helpers. NOTE: filename still carries the old
│                                  "wp_blogger" ("wpb") prefix even though app_id/display_name
│                                  were renamed to "article-writer"/"Article Writer" — cosmetic
│                                  leftover, not a bug, but inconsistent with the rest of the
│                                  naming (see Known Gaps).
├── params.py                   — all chat-function Pydantic param models (200 lines)
├── response_models.py          — all data_model response Pydantic models (141 lines)
├── skeleton.py                 — 4 @ext.skeleton functions (167 lines)
├── api_client.py                — HTTP client to the per-user `backend_url` MOS-style backend;
│                                  also home of the Matomo IPC calls (484 lines — over the
│                                  300-line project limit)
├── api_seranking.py             — SE Ranking header/base-URL constants — DEAD CODE, not
│                                  imported anywhere in the repo (verified via repo-wide grep)
├── api_wordpress.py             — WordPress REST API client (create/update/get/search/list
│                                  posts, verify_connection) — actually used, called directly
│                                  from handlers_publish.py, not proxied through backend_url
├── handlers_nav.py               — 18 chat functions: view/tab navigation, open/resume editor,
│                                  new_content, import_from_wp (308 lines — over limit)
├── handlers_content.py           — 10 chat functions: save_draft, update_status, delete_content,
│                                  generate_brief/save_brief, patch_article, quality check, list,
│                                  migrate_from_store, show_article (493 lines — over limit)
├── handlers_ai_write.py          — 2 chat functions: ai_write (main AI generation),
│                                  check_article_job (background-job fallback) (297 lines)
├── handlers_ai_extra.py          — 2 chat functions: improve_article, generate_newsletter (134 lines)
├── handlers_seo.py               — 9 chat functions: SE Ranking keyword/gap/rank fetch, project
│                                  list, content-plan builder, blog style setup, GSC report +
│                                  OAuth connect + credential save (594 lines — over limit)
├── handlers_publish.py           — 16 chat functions: all WordPress publish/update/list/delete/
│                                  unpublish, Rank Math SEO, save_settings/get_settings, keyword
│                                  add-to-article, SEO meta check (1155 lines — by far the
│                                  largest file, ~4x the project's 300-line limit)
├── handlers_docs.py              — 3 chat functions: upload_doc/delete_doc/list_docs
│                                  (knowledge-base files used as AI writing-style context);
│                                  has a redundant duplicate `ActionResult` import (harmless,
│                                  just messy — `from imperal_sdk import ActionResult` then
│                                  `from imperal_sdk.types import ActionResult  # noqa: F811`)
├── handlers_keywords.py          — 3 chat functions: add/remove/list SE Ranking tracked keywords
├── panels_side.py                — LEFT panel "sidebar": nav buttons, pipeline counts, quick
│                                  add-item form, recent articles list
├── panels_workspace.py           — CENTER panel "editor" (the only other @ext.panel besides
│                                  sidebar): router by `active_view` param → plan (default) /
│                                  editor / rankings / keywords / settings / docs views. Also
│                                  contains the plan/rankings/keywords view render code inline
│                                  (609 lines — over limit)
├── panels_editor.py               — editor_view() — article editor UI (brief + article HTML,
│                                  WordPress link, GSC page-detail if connected); dispatches to
│                                  the newsletter editor when item type == "newsletter"
│                                  (322 lines — over limit)
├── panels_editor_newsletter.py     — newsletter-specific editor view, split out of panels_editor.py
├── panels_editor_helpers.py        — pure HTML-rendering helpers (brief/article preview) for
│                                  panels_editor.py
├── panels_docs.py                 — Knowledge Base view: upload/list/delete brand doc files,
│                                  includes a canned "onboarding prompt" the user can paste into
│                                  chat to have Webbee help them draft a brand doc
├── panels_settings_view.py        — Settings view: Backend Bridge, SE Ranking, WordPress, GSC,
│                                  Brand Identity forms — all via plain `ui.Input` + `save_settings`
│                                  (196 lines)
├── panels_article_info.py         — 2-line stub: "no custom panel registered — platform
│                                  auto-manages the right slot." Effectively dead/no-op.
├── panels_right.py                — 2-line stub: "Panel moved to panels_article_info.py — do
│                                  not import or register panels here." Also dead/no-op — having
│                                  BOTH stub files is itself redundant (see Known Gaps).
├── icon.svg
├── imperal.json                   — manifest, 67 tools, matches source 1:1, matches live deploy
├── manifest.json                  — a SECOND, separate 62KB manifest-shaped file at repo root.
│                                  Its relationship to imperal.json is unclear from this pass —
│                                  worth confirming with whoever last touched it before assuming
│                                  it's safe to delete.
├── wp_blogger.egg-info/           — Python package metadata directory named "wp_blogger" —
│                                  another leftover from the pre-rename "WP-Blogger" project name.
├── IMPERAL_SDK_COMPLETE_REFERENCE.md, README.md — pre-existing docs, not verified line-by-line
│                                  against current code in this pass; treat as historical context
│                                  rather than current truth.
└── tests/
    ├── test_plan.py    — 7 tests (content plan nav, new_content, save_draft, update_status ×2, editor_mode)
    ├── test_publish.py — 10 tests (WP publish guards, save_settings, content-prep helpers)
    └── test_seo.py     — 5 tests (SE Ranking/GSC guard conditions, keywords view nav)
```

**7 files exceed the workspace's 300-line-per-file rule**: `handlers_publish.py` (1155),
`panels_workspace.py` (609), `handlers_seo.py` (594), `handlers_content.py` (493),
`api_client.py` (484), `panels_editor.py` (322), `handlers_nav.py` (308). This is very likely a
real contributor to the live "Does not meet quality standards" rejection (the same class of
issue that blocked matomo-analytics-extension's first deploy attempt this session).

---

## Chat-function inventory (63 functions + 4 skeleton tools = 67, matches manifest)

Grouped by handler file. `action_type` and description text below are copied verbatim from each
`@chat.function(...)` decorator, not paraphrased from memory.

### `handlers_nav.py` (18, all `action_type="read"` except `new_content`/`import_from_wp`)
Pure UI-state navigation — every one calls `save_ui_state()` and returns `NavStateResponse`:
`go_plan`, `go_plan_ideas`, `go_plan_writing`, `go_plan_review`, `go_plan_done`, `go_rankings`,
`go_keywords`, `go_settings`, `go_docs`, `open_editor(content_id)`, `set_editor_mode(mode)`,
`go_preview`, `go_edit`, `show_editor_panel`, `hide_editor_panel`, `resume_editor`.
Two write actions: `new_content(keyword, type, title, volume, difficulty)` — creates an empty
plan item and opens it; `import_from_wp(post_id | keyword_hint, instruction?)` — imports a WP
post and optionally edits it in the same call.

### `handlers_content.py` (10, `action_type="write"` except `list_articles`)
`save_draft(content_id, title, content, subject)` — persists editor HTML.
`update_status(content_id, status)` — idea/writing/review/published.
`delete_content(content_id)`.
`generate_brief(content_id, extra?)` / `save_brief(content_id, brief_text)` — SEO brief
(title, meta description, H2/H3 outline, search intent).
`patch_article(instruction, content_id?, keyword_hint?)` — targeted edit of part of an article.
`check_article_quality` — **script-based, zero-AI-token** audit (word count, heading structure,
comparison table, FAQ, outbound links).
`list_articles` — read.
`migrate_from_store` — one-time migration of legacy ctx.store content into the MOS backend.
`show_article` — dumps full article text into chat.

### `handlers_ai_write.py` (2)
`ai_write(content_id?, section="full"|"improve", article_type?)` — the main AI generation call
(`action_type="write"`). `check_article_job` — fallback to retrieve a job that was running in a
previous session if `ai_write` was interrupted.

### `handlers_ai_extra.py` (2, both `write`)
`improve_article(content_id?, instruction?)` — full rewrite/improve pass.
`generate_newsletter(content_id?, news_text, tone_note?)` — brand-voice newsletter writer.

### `handlers_seo.py` (9)
`fetch_keywords(domain?, source?, limit=80, min_volume=50, max_difficulty=70)` — SE Ranking
keyword research (`read`). `fetch_gaps(competitor, source="us", limit=30)` — competitor gap
analysis. `fetch_rankings` — organic Google positions from SE Ranking (explicitly NOT Microsoft
Ads/paid). `list_ser_projects` — find project_id for Settings. `build_content_plan(competitor?,
language="en")` — generates a 5-article plan from SE Ranking data + AI, avoiding already-published
topics (`write`). `setup_blog_style(blog_url?)` — analyzes a blog URL to build a writing-style
profile. `gsc_report` — clicks/impressions/CTR/position/top pages/queries/anomalies from Search
Console. `gsc_connect_oauth` — Google OAuth2 connect flow (paste `credentials.json` → auth URL).
`save_gsc_credentials(site_url, credentials_json)` — direct credential save, bypassing OAuth.

### `handlers_publish.py` (16 — the largest handler file by far)
`publish_wp(content_id, status="draft"|"publish")` — generic create/update.
`publish_wp_draft` / `publish_wp_publish` — explicit draft-only / live-only variants.
`set_wp_seo(content_id?, keyword_hint?, meta_description?, focus_keyword?)` — Rank Math SEO,
call after publish. `save_settings(...)` / `get_settings` — the extension's own settings form
backing (see Settings section below — `get_settings` masks keys before returning them).
`list_wp_posts(status="any", per_page=20)` — read-only WP post listing.
`unpublish_wp(content_id?, keyword_hint?)` — sets a post back to draft.
`get_article_link(title_or_keyword)` — find a post's URL on the user's own blog.
`get_wp_post_content` — full text of a WP post/draft.
`rewrite_article(content_id?, instruction?)` — full from-scratch rewrite.
`add_keywords_to_article(keywords, content_id?)` — adds keywords + updates Rank Math.
`check_seo_meta(content_id?, keyword_hint?)` — Rank Math focus/secondary keywords, meta
description, keyword density, word count, WP status.
`patch_wp_article(...)` / `edit_wp_article(...)` — edit-by-WP-post-ID variants of patch_article/
import_from_wp+edit. `delete_wp_post` — permanent delete (moves to trash).

### `handlers_docs.py` (3)
`upload_doc(files)` — base64 files from `ui.FileUpload`. `delete_doc(doc_id)`. `list_docs` (`read`).

### `handlers_keywords.py` (3)
`add_tracked_keyword` / `remove_tracked_keyword` / `list_tracked_keywords` — SE Ranking position
tracking list management (distinct from `fetch_keywords`' one-off research).

### Skeleton tools (`skeleton.py`, 4)
`skeleton_refresh_current_article` (ttl 30s) — open article in editor: id/keyword/title/status/
word count. `skeleton_refresh_content_overview` (ttl 120s) — plan totals by status.
`skeleton_refresh_wp_config` (ttl 600s) — WordPress/SE Ranking/GSC/Matomo connection status +
brand info (see Matomo IPC caveat above — `matomo_url` in this response is always empty right
now). `skeleton_refresh_content_list` (ttl 60s) — full article list summary for Webbee routing.

---

## Settings / secrets model — plain `ctx.store`, no EXT-SECRETS-V1

**Confirmed: `imperal.json`'s `"secrets"` field is `null` — this extension declares zero
`@ext.secret(...)` entries.** Every credential lives as a plain field in `ctx.store` via
`wpb_app.py::DEFAULT_SETTINGS`/`load_settings`/`save_settings`:

```python
DEFAULT_SETTINGS = {
    "backend_url": "", "backend_api_key": "",
    "seranking_api_key": "", "seranking_project_id": "", "seranking_domain": "", "seranking_source": "us",
    "wp_url": "", "wp_username": "", "wp_app_password": "", "wp_author_id": 1,
    "gsc_site_url": "sc-domain:webhostmost.com", "gsc_credentials_json": "",
    "gsc_service_account": "", "gsc_oauth_client_id": "", "gsc_oauth_client_secret": "", "gsc_oauth_refresh_token": "",
    "company_name": "", "brand_description": "", "brand_voice": "...", "newsletter_cta": "...",
    "site_url": "", "blog_url": "", "tg_url": "", "community_url": "",
}
```
(Note the default `gsc_site_url` is hardcoded to `sc-domain:webhostmost.com` — a WebHostMost-
specific default baked into a multi-tenant extension's defaults; every other installer would see
this as their starting value unless they overwrite it.)

`panels_settings_view.py` renders these as plain `ui.Input` fields (**not** `ui.Password`/
`type="password"`) inside per-section `ui.Form`s (`backend_url`/`backend_api_key`,
`seranking_*`, `wp_*`, GSC block, brand-identity block). For fields that already have a saved
value, the placeholder shows a masked hint via a local `_masked()` helper
(`"••••" + last 4 chars`) instead of echoing the real value into `value=` — so an already-saved
secret isn't visible on screen, but a freshly-typed one is (no password-masking while typing).
`get_settings` (the chat-facing read) also masks properly (`sv[:4] + "***" + sv[-4:]`) before
returning to Webbee/chat.

**This is the same class of gap matomo-analytics-extension had before this session's
EXT-SECRETS-V1 migration** — credentials here (`backend_api_key`, `seranking_api_key`,
`wp_app_password`, `gsc_credentials_json`, `gsc_oauth_client_secret`, `gsc_oauth_refresh_token`)
are real per-user secrets that would benefit from the same treatment (platform Secrets vault +
auto-generated Secrets panel), but that migration has not been done here.

---

## Panels

Only **two** `@ext.panel(...)` registrations exist in the whole repo (verified by grep, not by
filename — several files that sound like panels, `panels_editor.py`/`panels_editor_newsletter.py`/
`panels_docs.py`/`panels_settings_view.py`, are view-renderer modules imported *by* the panels
below, not separate registered panels themselves):

- **`sidebar`** (slot `left`, `panels_side.py`) — nav buttons (Content Plan/Rankings/Keyword
  Research/Brand Knowledge/Settings), integration status badges (SE Ranking/WordPress/GSC,
  no Matomo badge here), pipeline counts by status, quick "+ New item" form, recent-articles list
  with click-to-open. Sets `auto_action` to open the center panel on first load.
- **`editor`** (slot `center`, `center_overlay=True`, `panels_workspace.py`) — a single router
  panel dispatching on the `active_view` param to 6 views: `plan` (default — kanban-style content
  queue), `editor` (article editor, itself dispatching to the newsletter editor when
  `item.type == "newsletter"`), `rankings`, `keywords`, `settings`, `docs`.

**No right-slot panel** — `panels_article_info.py` and `panels_right.py` are both explicit no-op
stub files with comments saying the platform auto-manages that slot; having two separate stub
files for the same "nothing here" statement is itself redundant.

---

## Tests

22 tests, all passing (`pytest tests/ -q` via the shared
`SeeU-Extensions/.venv-ext` venv — imperal_sdk 5.9.3, pytest 9.1.1):
- `test_plan.py` (7) — nav/new_content/save_draft/update_status (+invalid)/editor_mode
- `test_publish.py` (10) — WP-publish guard conditions (no key/empty content/missing item),
  save_settings (+ partial update), category-pick + content-prep helper unit tests
- `test_seo.py` (5) — SE Ranking/GSC "not configured" guards, keywords-view nav

**Coverage is thin relative to the 63-function surface.** Zero tests found for: `ai_write`,
`improve_article`, `generate_newsletter`, `check_article_job`, `patch_article`,
`check_article_quality`, `list_articles`, `migrate_from_store`, `show_article`, all of
`handlers_docs.py`, all of `handlers_keywords.py`, `build_content_plan`, `setup_blog_style`,
`gsc_report`/`gsc_connect_oauth`/`save_gsc_credentials`, and 12 of `handlers_publish.py`'s 16
functions (only `save_settings`/`publish_wp` guard-paths are covered).

---

## Known gaps (verified, not speculative)

1. **7 files over the 300-line project limit**, `handlers_publish.py` at 1155 lines being the
   most extreme — almost certainly part of why the live app is stuck in `draft` /
   "Does not meet quality standards".
2. **No EXT-SECRETS-V1** — all credentials in plain `ctx.store`, unmasked `ui.Input` for entry.
3. **Matomo IPC contract drift**: `matomo_config` IPC calls in `api_client.py` and `skeleton.py`
   read a `matomo_url`/`matomo_token` shape that the Matomo Analytics Connector extension no
   longer returns (removed for security in this session) — those two read-paths are silently
   broken right now (the `growing_pages` IPC call is unaffected).
4. **`SaveSettingsParams` still declares `matomo_url`/`matomo_token`/`matomo_site_id`** fields
   that nothing in `wpb_app.py` reads back out of storage — dead params.
5. **`api_seranking.py` (131 lines) is dead code** — not imported anywhere in the repo.
6. **Two duplicate manifest-shaped files** at repo root: `imperal.json` (current, matches source
   and live deploy) and a separate `manifest.json` (62KB) whose purpose/currency wasn't
   established in this pass.
7. **Legacy naming**: `wpb_app.py` (should logically be `app.py` to match every other extension
   in this workspace), `wp_blogger.egg-info/` — both leftover from the pre-rename
   "WP-Blogger" project name; cosmetic, not functional bugs.
8. **Two redundant right-panel stub files** (`panels_right.py`, `panels_article_info.py`) saying
   the same "nothing registered here" thing.
9. **Hardcoded WebHostMost-specific default**: `DEFAULT_SETTINGS["gsc_site_url"] =
   "sc-domain:webhostmost.com"` — every fresh install starts pointed at WebHostMost's own GSC
   property rather than an empty/neutral default.
10. **Test coverage** covers guard-conditions and nav well but has zero coverage on the AI
    writing, GSC, docs, and keyword-tracking function families (see Tests section).
