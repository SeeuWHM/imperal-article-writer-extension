# Article Writer Extension — Full Documentation

**Version:** 2.1.1 (code HEAD `728c047`; prod active v2.0.0 — redeploy pending) | **app_id:** `imperal-article-writer-extension` |
**tool_name:** `article_writer`
**Git:** `github.com/SeeuWHM/imperal-article-writer-extension`
**Backend:** `SeeU-Extensions/article-writer-backend/` (single source of truth for the backend —
schema, API surface, generation pipeline, deploy status). This doc covers the extension side only.

This is a **from-scratch rebuild**, not an iteration on the old code. The old extension (63
functions, 7 files over the 300-line limit, no EXT-SECRETS-V1, tangled SE Ranking/WordPress/GSC/
Matomo integrations, backed by a since-decommissioned single-tenant service at `/opt/articles-writer`)
was deleted wholesale. Nothing below references it — see git history before `2026-07-13` if that
context is ever needed.

---

## What this actually is

A **project-based SEO article writer**, deliberately narrow in scope:

- A **project** is a per-site context container: name, site URL, description, keywords, useful
  links, social links, brand voice. Webbee fills this in using web search and whatever other
  extensions the user has installed (SE Ranking, GSC, Matomo, etc.) — this extension has **no
  idea those exist**. It only stores whatever context it's handed.
- An **article** belongs to a project and moves through `idea → writing → review → published`.
  Webbee never writes article bodies directly — it calls `generate_article` (full pipeline:
  outline → draft → mechanical gates → grounding → judge → targeted revision) or `patch_article`
  (locate one section by instruction → edit just that section → rescore), both of which hand off
  to the backend's real generation pipeline.
- **Full article bodies are read/edited exclusively in the panel** (`panels_workspace.py`), via
  plain server-side Python calling the backend directly — zero LLM tokens, any corpus size.
  **No chat.function in this extension ever returns a full article body** — this is a structural
  guarantee, not a convention: `response_models.ArticleSummary` (used by every list/status
  function) has no `content`/`sections` field to receive one into, even if the backend's response
  happened to include one. See that model's docstring.

Everything else — SE Ranking, Rank Math, GSC, WordPress publishing — is explicitly **out of
scope**, left to separate extensions that Webbee orchestrates on its own.

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (18) or panel action
handlers_projects.py / handlers_articles.py / handlers_generate.py
    ↓ HTTP (api_client.call_backend, GET/POST/PATCH/PUT/DELETE) — Bearer backend_jwt + X-Imperal-Id header
      article-writer-api (shared backend microservice, api-server:8017)
      Galera-backed (imperal_article_writer db) — see article-writer-backend/PLAN.md
```

`article-writer-api.service` is **live** on `127.0.0.1:8017` on api-server, exposed publicly via an
nginx route at `api.webhostmost.com/article-writer/`. Proven end-to-end with real generations
(real Anthropic spend, ~$0.08–0.10/article) — not just a health-check ping.

Two credentials travel on every backend call (`api_client.py`):
- `backend_jwt` — `ext.secret(scope="app")`, developer-managed, identical for every installer.
  Authenticates **this extension** to the backend. Never entered or seen by end users.
- `X-Imperal-Id` header — `ctx.user.imperal_id`, the caller's own canonical platform identity.
  The backend scopes every table query to this value. Unlike se-ranking-connector (which forwards
  a per-user *external* API key because SE Ranking tenancy is by external account), there is no
  external account here — tenancy is purely by platform identity, so no user-facing secret exists
  in this extension at all.

No cross-extension IPC calls exist anywhere in this codebase — this extension is a thin, honest
client of one backend and nothing else.

---

## File structure

```
article-writer-extension/
├── main.py                 — entry point; hot-reload module list
├── app.py                  — Extension + ChatExtension init, backend_jwt secret, health check
├── api_client.py           — call_backend(): the one HTTP client every handler/panel/skeleton uses
├── params.py                — all chat-function Pydantic param models (mirror backend request schemas exactly)
├── response_models.py       — all data_model response Pydantic models (ArticleSummary is structurally body-free)
├── richtext.py               — plain-text/light-markdown <-> HTML conversion for the RichEditor panel
├── navstate.py               — tiny ctx.store nav doc (view/project_id/article_id) shared by both panels
├── skeleton.py               — 1 @ext.skeleton: project/article counts by status, degrades to zeros
├── handlers_projects.py      — create_project, list_projects, update_project_context, delete_project
├── handlers_articles.py      — create_article, list_articles, update_article_status, update_article_meta,
│                                save_article_section, save_full_article, delete_article, export_article_text
├── handlers_generate.py      — generate_article, check_generation_status, patch_article
├── panels_side.py            — LEFT panel "sidebar": active-project detail + compact project switcher
├── panels_workspace.py       — CENTER panel "workspace": article board (by status) + single-editor article view
├── icon.svg
├── imperal.json               — manifest, regenerated by `imperal build`
├── pyproject.toml
└── tests/
    ├── test_handlers.py       — 20 tests, MockContext + monkeypatched call_backend (no network)
    └── test_richtext.py       — 22 tests, pure-function round-trip tests, no ctx/network at all
```

`richtext.py` bridges the backend's stored format (plain text with light markdown — `**bold**`,
`*em*`, `- ` bullets, `[text](url)` links — exactly what the generation pipeline's prompts produce)
and the panel's `ui.RichEditor` (TipTap), whose `content` prop is an HTML string. `navstate.py` is
how the sidebar knows which project is "open" in the center panel without the two panels holding
any direct reference to each other — written by `panels_workspace.py` on every render, read by both.

Every file is under the workspace's 300-line limit. No dead code, no duplicate manifest files, no
legacy naming leftovers.

---

## Chat-function inventory (18 functions)

### `handlers_projects.py`
- `create_project(name, site_url?, description?, keywords?, useful_links?, social_links?, brand_voice?)` — write
- `list_projects()` — read, `chain_callable=True`
- `update_project_context(project_id, ...any field...)` — write, requires ≥1 field
- `delete_project(project_id)` — destructive, cascades to articles
- `add_reference_link(project_id, url, description)` — write, **new (v2.1.0)**. One internal page of the project's own site as an interlinking target, stored `{url, description}` (deduped by url). See Internal linking below.
- `list_reference_links(project_id)` — read, `chain_callable=True`, **new**. The project's reference links (url + description).
- `remove_reference_link(project_id, url)` — destructive, **new**. Removes one reference link by url.

### `handlers_articles.py`
- `create_article(project_id, title?, target_keyword?)` — write, empty shell only
- `list_articles(project_id?, status?)` — read, `chain_callable=True`, metadata only
- `update_article_status(article_id, status)` — write, `PATCH /v1/articles/{id}/status`
- `update_article_meta(article_id, title?, meta_description?, target_keyword?)` — write, **new**.
  Fixes SEO metadata (e.g. clears a "meta_description length outside 70–165" flag, corrects the
  target keyword) without touching body/sections — the only path that does that; body edits still
  go through `patch_article`.
- `save_article_section(article_id, order_index, heading?, content?)` — write, **raw manual
  overwrite, bypasses AI review entirely** — description explicitly steers Webbee toward
  `generate_article`/`patch_article` instead; usable from chat when a user pastes/dictates exact
  text.
- `save_full_article(article_id, content_html)` — write, **new, panel-only**. The single merged
  RichEditor's Save button — see Panels below. Splits the submitted HTML document back into
  sections at heading boundaries (`richtext.html_to_sections`), so adding/removing/reordering a
  heading in the editor is how sections get added/removed/reordered. Not for chat use.
- `delete_article(article_id)` — destructive
- `export_article_text(article_id)` — read, **new**. The one deliberate exception to "never return
  a full body to chat" (see `response_models.ArticleFullText`'s docstring) — for handing an article
  to another extension (email it, save it as a note, paste it elsewhere). Returns **both** `text`
  and `html`; **both fields are a hard requirement, not optional convenience**: a 2026-07-15
  version that dropped `text` and kept only `html` broke a real production email — something in
  the kernel's cross-tool value-passing was keyed to a field literally named `text`, and losing it
  silently sent a raw, unresolved `{{article_text_latest}}` placeholder to a real recipient instead
  of the article. Both fields must be populated permanently; do not remove either without first
  confirming what depends on it.

### `handlers_generate.py`
- `generate_article(article_id, brief, target_keyword?, source_snippets?)` — write, enqueues the
  backend's async pipeline, returns `{job_id, article_id, status}`
- `check_generation_status(article_id, job_id)` — read, `chain_callable=True`
- `patch_article(article_id, instruction, section_hint?)` — write, synchronous, returns
  `{section_id, order_index, heading, preview, word_count, seo_flags}` — never the full body

### Skeleton (`skeleton.py`, 1)
`article_writer_overview` (ttl 60s) — project count, article count by status, degrades to zeros
with a friendly instruction if the backend is unreachable (never blocks or errors).

---

## Internal linking (reference links) — v2.1.0

Each project stores a list of **reference links** — internal pages of its own site the writer may
link to — as `{url, description}` objects (`reference_links` on the backend project;
`ProjectRecord.reference_links` here; managed from chat via `add_reference_link` /
`list_reference_links` / `remove_reference_link`). The `description` is the page's topic; the
backend's generation pipeline uses it to build a **natural, varied, in-sentence anchor** (e.g.
"…they were missing a `[reliable hosting plan](url)` to get their sites to the top…") — never an
invented URL, never the bare brand/domain, never a bolted-on "keyword(link) is X" label. Webbee is
expected to collect these from the site's own pages (GSC top pages, SE Ranking tracked pages, a
sitemap). All prompt + validation logic lives in the **backend** (`article-writer-backend/PLAN.md`
§6b) — this extension only stores/reads the list. Links round-trip through `richtext.py` and are
preserved on save and in both `export_article_text` fields.

---

## Secrets model — EXT-SECRETS-V1, one secret

`imperal.json`'s `secrets` array has exactly one entry:

```python
ext.secret(
    name="backend_jwt", required=True, scope="app",
    env_fallback="IMPERAL_APPSECRET_ARTICLE_WRITER_BACKEND_JWT", max_bytes=2048,
)
```

Developer-set only, via `developer.save_app_secret` (or the `IMPERAL_APPSECRET_*` env fallback for
local dev) — never entered or visible to end users. There is **no per-user secret** in this
extension (see Architecture above for why).

**Known local-tooling gap**: `imperal validate` reports 2 errors —
`[M3] [secrets.0.scope] Extra inputs are not permitted` and the same for `env_fallback`. This is
**not a defect in this extension's code**: `scope`/`env_fallback` are real, documented fields on
the SDK's own `SecretSpec` (`imperal_sdk/secrets/spec.py`, EXT-SECRETS-V1 v4.2.2+) and the
manifest writer (`imperal_sdk/manifest.py`) faithfully serializes them — but the local CLI's `M3`
manifest-schema check hasn't been updated to accept them. Verified this is universal, not specific
to this extension: running `imperal validate` against the already-deployed, working
`se-ranking-extension` (which declares `backend_jwt` the exact same way) produces the identical
two errors. Reported to Ignat to pass along to the SDK developer — do not "fix" this by dropping
`scope="app"`, which would silently turn `backend_jwt` into a per-user secret and break the whole
shared-backend-auth design.

---

## Panels

- **`sidebar`** (slot `left`) — shows **full context (name, site URL, description, keywords) only
  for the project currently open** in the center panel (`navstate.load_nav` tells it which one).
  Every other project renders as a compact clickable row (`ui.ListItem`, name + site URL,
  `on_click` → routes the center panel to that project's article board) — there's no reason to
  show every project's whole keyword list when only one is actually being worked on. Those rows
  are wrapped in a real `ui.List`: a bare `ui.ListItem` as a direct `Stack` child made the whole
  sidebar vanish (live 2026-07-14 incident) — `ListItem` must always live inside a `List`. Below
  the project section, a minimal "+ New project" form (name/site_url/keywords only — the rest of a
  project's context is filled in later via chat's `update_project_context`, by design).
- **`workspace`** (slot `center`) — two views, routed via the SDK's `__panel__workspace` synthetic
  action (plain kwargs `view`/`project_id`/`article_id`, no LLM involved — see
  `imperal_sdk.Extension.panel`'s docstring):
  - `articles` — board grouped by status. No "+ New article" form here anymore — Webbee creates
    articles via chat (`create_article`); this view is navigation only, it doesn't duplicate
    actions Webbee already owns.
  - `article` — header/status/flags, then a `generate_article` form if no sections exist yet, or
    **one single merged `ui.RichEditor`** if they do — every section's heading and body rendered as
    one seamless document (`richtext.sections_to_html`), not N separate per-section plaintext
    boxes. Its Save button submits the whole document to `save_full_article`, which splits it back
    into sections at heading boundaries. There's no "Patch with AI" form anymore either — rewriting
    content by instruction is Webbee's job via chat (`patch_article`); the panel edits directly and
    doesn't duplicate that. The status-change form and the delete button sit **side by side in one
    row** right under the header (not stacked, and delete is no longer buried at the bottom of the
    document).

  Section headings in the editor are always **H2** — one H1 per page is correct SEO practice, and
  the article's own title field already is the page's H1. The HTML parser accepts H1/H2/H3 as
  section boundaries for robustness (the editor's toolbar exposes all three), but
  `sections_to_html` always re-emits H2 on the way back out.

  **Known SDK/frontend gap, not fixable from this extension**: `richtext.py` converts markdown
  links (`[text](url)`) to/from real `<a href>` tags, but the RichEditor's TipTap toolbar exposes no
  link-insertion button — confirmed against `imperal/platform/docs/imperal-panel.md`, where
  `ui.Link` is a separate standalone SDK component, not an inline mark inside `RichEditor`. A user
  can still type/paste a markdown link and it round-trips correctly; there's just no toolbar button
  to insert one from inside the editor.

  A tiny `article_writer_nav_state` doc in `ctx.store` (`navstate.py`) remembers the last-open
  position across a plain reload — it holds only IDs/view name, never article content, and both
  panels read/write it as a convenience only (never load-bearing — failures are swallowed).

---

## Tests

42 tests, all passing (`../.venv-ext/bin/python -m pytest tests/ -q`):

- **`test_handlers.py` (20)** — project CRUD (create/list/update-requires-a-field/delete), article
  CRUD (create/list/update-status/update-meta-requires-a-field/update-meta/save-section-requires-
  a-field/save-section/save-full-article-splits-by-heading/delete/export-returns-html), generation
  (start/check-status), patch (returns preview, structurally excludes body/sections), and
  `api_client.call_backend`'s missing-JWT config guard. `test_list_articles_never_carries_body`
  and `test_export_article_text_returns_html` explicitly assert the token-economy guarantee: every
  function stays body-free except the one deliberate exception, which always carries both `text`
  and `html`.
- **`test_richtext.py` (22)** — pure round-trip tests for `richtext.py`, no ctx/network at all:
  `to_html`/`from_html` paragraph/bold/italic/list/link conversion and round-trips, bullet-merging
  across blank lines, `sections_to_html`/`html_to_sections` round-trips including H1/H3 boundary
  handling and heading-less leading content, and `to_export_text`'s markdown-stripping.

---

## Open items (not yet done — tracked here, not invented as future work elsewhere)

1. **Developer Portal app registration is stale — urgent.** The Developer Portal's
   `display_name`/`description`/`pricing_config` for this app still advertise the **old, deleted**
   47-function surface (`show_article`, `publish_wp`, `gsc_connect_oauth`, `ai_write`, etc.), even
   though `imperal.json`'s actual `tools` list is correct (15 real functions + skeleton refresh).
   The Developer Portal registration is separate from the code manifest and isn't derived from it,
   so this drifted silently. Effect observed live: Webbee sometimes hallucinates/repeatedly
   attempts calling nonexistent functions like `show_article` because the portal's description
   still tells it those exist — one observed turn burned 320,801 tokens mostly on this. Needs a
   manual fix in the Developer Portal (Ignat) to match the real 15-function set.
2. **RichEditor has no link-insertion button** (SDK/frontend gap, not fixable from this
   extension) — see Panels above. Worth relaying to the SDK developer if `ui.Link` functionality
   is ever meant to be reachable from inside `ui.RichEditor`.
3. **Deployed & active, but prod is behind code.** The app is deployed/active in the Developer
   Portal at **v2.0.0**; current code HEAD is **`728c047` (v2.1.1)** — the reference-links functions
   and the new quill/feather icon land only on the next git → Developer Portal redeploy.
4. Backend-side open items — see `article-writer-backend/PLAN.md` (source of truth for the
   backend); this doc doesn't duplicate that list.
