# Article Writer Extension — Full Documentation

**Version:** 2.4.1 (code HEAD `d403368`; prod active **v2.0.0** — Dev Portal redeploy pending) |
**app_id:** `imperal-article-writer-extension` | **tool_name:** `article_writer`
**Git:** `github.com/SeeuWHM/imperal-article-writer-extension`
**Backend:** `SeeU-Extensions/article-writer-backend/` (single source of truth for the backend —
schema, API surface, generation pipeline, deploy status). This doc covers the extension side only.

> **Resume point (2026-07-17).** Everything below reflects the real code at HEAD, not aspiration.
> The code is pushed; **prod still runs v2.0.0** until the next Developer Portal git deploy. The
> backend `article-writer-api` on api-server was **not** changed today (only the extension was).

---

## What this actually is

A **project-based SEO article writer**, deliberately narrow in scope:

- A **project** is a per-site context container: name, site URL, description, keywords, useful
  links, social links, brand voice, reference links. Webbee fills this in using web search and
  whatever other extensions are installed (SE Ranking, GSC, Matomo…) — this extension has **no idea
  those exist**; it only stores whatever context it's handed.
- An **article** belongs to a project and moves `idea → writing → review → published`. It is written
  by the backend pipeline, never by hand in chat: `generate_article` (outline → draft → mechanical
  gates → grounding → judge → targeted revision) or `patch_article` (locate one section → rewrite
  just it).
- **The title is the leading `# ` (H1) of the single editor document.** Section headings are `## `
  (H2). There is no separate title field — the title lives inside the same editor/markdown as the
  body, and what is the title vs the body is decided on save (first H1 = title).
- **Webbee can now read and edit the full text** (owner-requested, 2026-07-17): `read_full_article`
  returns the whole body as editable Markdown, `edit_full_article` replaces it verbatim from
  submitted Markdown. This is a deliberate relaxation of the old "chat never sees the body" rule.
  The metadata list functions (`list_articles`, etc.) still stay body-free by design
  (`ArticleSummary` has no `content`/`sections` field).

Out of scope (other extensions Webbee orchestrates): SE Ranking, GSC, WordPress publishing, Rank Math.

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (20) or panel action
handlers_projects.py / handlers_articles.py / handlers_generate.py / handlers_edit.py
    ↓ HTTP (api_client.call_backend) — Bearer backend_jwt + X-Imperal-Id header
      article-writer-api (shared backend microservice, api-server 127.0.0.1:8017)
      public route: api.webhostmost.com/article-writer/   ·   Galera db imperal_article_writer
      (pipeline/schema/deploy → article-writer-backend/PLAN.md)
```

Two credentials on every backend call (`api_client.py`):
- `backend_jwt` — `ext.secret(scope="app")`, developer-managed, identical for every installer;
  authenticates **this extension** to the backend. Never entered/seen by end users.
- `X-Imperal-Id` — `ctx.user.imperal_id`; the backend scopes every query to it. Tenancy is purely
  by platform identity (no external per-user account, so no user-facing secret exists here).

No cross-extension IPC anywhere — a thin, honest client of one backend.

---

## File structure

```
article-writer-extension/
├── main.py               — entry point; hot-reload module list (imports handlers_edit too)
├── app.py                — Extension + ChatExtension init, backend_jwt secret, health check
├── api_client.py         — call_backend(): the one HTTP client every handler/panel/skeleton uses
├── params.py             — chat-function Pydantic param models (mirror backend request schemas)
├── response_models.py    — data_model response models (ArticleSummary is structurally body-free;
│                            ArticleFullText = export; ArticleTextRecord = read-for-edit markdown)
├── richtext.py           — text/markdown <-> HTML (panel) AND markdown <-> document (Webbee edit):
│                            sections_to_html/html_to_sections, document_to_html/html_to_document,
│                            document_to_markdown/markdown_to_document
├── navstate.py           — tiny ctx.store nav doc (view/project_id/article_id)
├── skeleton.py           — @ext.skeleton(alert=True) refresh + paired skeleton_alert_* tool
├── handlers_projects.py  — project CRUD + reference links
├── handlers_articles.py  — article CRUD, status/meta, save_section, save_full (panel), export
├── handlers_generate.py  — generate_article, check_generation_status, patch_article
├── handlers_edit.py      — read_full_article, edit_full_article (Webbee full-text read/edit) [NEW]
├── panels_side.py        — LEFT "sidebar": active-project detail + compact project switcher
├── panels_workspace.py   — CENTER "workspace": article board + single-editor article view (H1 title)
├── icon.svg · imperal.json · pyproject.toml
└── tests/  test_handlers.py · test_richtext.py · test_edit.py   (58 tests, all green)
```

Every file is under the 300-line limit (that's why read/edit went into a new `handlers_edit.py`).

---

## Chat-function inventory (20 functions + 2 skeleton tools)

### Projects (`handlers_projects.py`)
- `create_project(name, site_url?, description?, keywords?, useful_links?, social_links?, brand_voice?)` — write
- `list_projects()` — read, `chain_callable=True`
- `update_project_context(project_id, …any field…)` — write, ≥1 field
- `delete_project(project_id)` — destructive, cascades to articles
- `add_reference_link(project_id, url, description)` / `list_reference_links(project_id)` /
  `remove_reference_link(project_id, url)` — internal-page interlinking targets `{url, description}`

### Articles (`handlers_articles.py`)
- `create_article(project_id, title?, target_keyword?)` — write, **empty shell only, no AI**
- `list_articles(project_id?, status?)` — read, metadata only (never the body)
- `update_article_status(article_id, status)` — write
- `update_article_meta(article_id, title?, meta_description?, target_keyword?)` — write; the only path
  that fixes SEO metadata without touching the body (also how `edit_full`/`save_full` persist the title)
- `save_article_section(article_id, order_index, heading?, content?)` — write, raw verbatim one-section overwrite
- `save_full_article(article_id, content_html)` — write, **PANEL-ONLY**. The editor's Save: first `<h1>` = title (→ meta), rest split into sections at heading boundaries
- `delete_article(article_id)` — destructive
- `export_article_text(article_id)` — read. The send-elsewhere export (email/notes): returns **both**
  `text` and `html`. 🔴 **Both fields are mandatory** — a 2026-07-15 version that dropped `text` sent a
  raw `{{article_text_latest}}` placeholder to a real recipient (kernel cross-tool passing keys on a
  field named `text`). Never remove either.

### Generation (`handlers_generate.py`)
- `generate_article(article_id, brief, target_keyword?, source_snippets?)` — write, enqueues async pipeline → `{job_id,…}`
- `check_generation_status(article_id, job_id)` — read
- `patch_article(article_id, instruction, section_hint?)` — write, synchronous, one-section NL rewrite; returns a preview, never the full body

### Webbee full-text read/edit (`handlers_edit.py`) — NEW v2.4.0
- `read_full_article(article_id)` — read. Returns the whole body as editable **Markdown**
  (`# title`, `## headings`, light-markdown body). Deliberately to chat, so Webbee edits the real text.
- `edit_full_article(article_id, content_markdown)` — write. Replaces the whole article from submitted
  Markdown, stored **verbatim** (`markdown_to_document` → sections + title via `/meta`; no
  re-generation — what Webbee sends is exactly what is stored). For a small change prefer `patch_article`.

### Skeleton (`skeleton.py`)
- `skeleton_refresh_article_writer_overview` — `alert=True`, ttl-hint 60s. Returns
  `{"response": {project_count, article_count, by_status, latest_ready, instruction}}` — flat scalars,
  counts from the paged `total`, `latest_ready` = title of the newest article in `review`.
- `skeleton_alert_article_writer_overview(ctx, old, new)` — fires when the `review` count rises (a
  generation finished) and returns a proactive "your article «…» is ready for review" notice; "" otherwise.

---

## Panels

- **`sidebar`** (left) — full context only for the project currently open (via `navstate`); every other
  project is a compact clickable row inside a real `ui.List` (a bare `ui.ListItem` as a direct Stack
  child once made the whole sidebar vanish — always wrap ListItem in a List). Minimal "+ New project" form.
- **`workspace`** (center), routed via `__panel__workspace` (plain kwargs, no LLM):
  - `articles` — board grouped by status (navigation only; Webbee creates via chat).
  - `article` — a `generate_article` form if no sections yet, otherwise **one single merged
    `ui.RichEditor`**: the **title is the leading `<h1>`**, each section heading an `<h2>`, all one
    seamless document (`richtext.document_to_html`). Save (`save_full_article`) splits the first `<h1>`
    back to the title and the rest to sections. A standalone title header is shown **only** in the
    empty/generate state (before there's an editor). Status control + delete sit in one row under the header.

**Known SDK/frontend gap (not fixable here):** the RichEditor's TipTap toolbar has no link-insertion
button (`ui.Link` is a separate SDK component, not an inline mark) — markdown links still round-trip if
typed/pasted. Relayed to the SDK developer.

---

## Proactivity (2026-07-17)

1. **"Article ready" notifications** — the skeleton runs `alert=True` with a paired
   `skeleton_alert_*` tool. On each refresh the kernel diffs the snapshot; when `review` count rises,
   the alert returns a short notice and Webbee surfaces it to the user unprompted. Latency = the
   skeleton refresh interval (code hint 60s; authoritative TTL is the platform Registry row, kernel
   default 300s — so ~1–5 min in practice).
2. **Proactive source data** — the chat description tells Webbee to proactively gather the real facts
   an article needs (prices, stats, specs, quotes) and pass them as `source_snippets` to
   `generate_article` (so claims are grounded, nothing invented), and to collect the site's own pages
   as `reference_links`. ⚠️ **Article Writer has NO fill-category store** — that mechanism (reusable
   items with condition notes) exists only in Newsletter Writer. Do not tell Webbee to use fill
   categories here (a v2.4.0 description bug did exactly that; fixed in v2.4.1).

---

## Secrets — EXT-SECRETS-V1, one secret

`ext.secret(name="backend_jwt", required=True, scope="app", env_fallback="IMPERAL_APPSECRET_ARTICLE_WRITER_BACKEND_JWT", max_bytes=2048)`.
Developer-set only. No per-user secret exists. **Known local-tooling gap:** `imperal validate` reports
2 `[M3]` errors on `scope`/`env_fallback` — these are real SDK `SecretSpec` fields the local CLI's
schema check hasn't caught up to (identical errors on the deployed se-ranking-extension). Do **not**
"fix" by dropping `scope="app"` — that would silently turn it into a per-user secret.

---

## Pricing (per_action) — current + recommendation

Prices are "tokens/credits per function call". Reality: only `generate_*` (multi-LLM pipeline) and
`patch_*` (2 LLM calls) spend backend LLM tokens; `read_full`/`edit_full`/`export` spend Webbee
context tokens ∝ body size; everything else is cheap DB. Frequently-called list/check functions must
stay cheapest.

Current AW prices and my suggested adjustments:
- `list_*`, `check_generation_status` = 10 ✓ (called constantly — keep cheapest)
- `create/update/delete/status/meta`, reference-link ops = 10–30 ✓
- `save_article_section`, `save_full_article` (PANEL, 0 LLM) = 20 → **consider 0/min** (panel edit was meant free)
- `read_full_article` = 200 → **120–150** (don't discourage the read Webbee now needs)
- `edit_full_article` = 100 → **≥ read** (editing outputs the whole body — costs more than reading it)
- `export_article_text` = 60 → **≥ read** (returns 2 copies text+html — shouldn't be cheaper than read)
- `patch_article` = 50 ✓
- `generate_article` = 800 ✓ (correct anchor — the heaviest op)

A typical edit cycle = `read_full` + `edit_full`, so the user pays for both — keep each moderate.

---

## Tests

58 tests (`../.venv-ext/bin/python -m pytest tests/ -q`): `test_handlers.py` (project/article CRUD,
generate/patch, title-in-editor save, body-free guarantees), `test_richtext.py` (HTML + document +
markdown round-trips, H1-title extraction), `test_edit.py` (read_full/edit_full read+persist,
empty-input guard).

---

## Open items

1. 🔴 **Dev Portal redeploy pending** — prod active **v2.0.0**; code HEAD **v2.4.1**. The single-editor
   H1-title, "article ready" alerts, and Webbee read/edit-full land only on the next git → Developer
   Portal deploy (Ignat).
2. 🔴 **Dev Portal app registration is stale** — its `display_name`/`description`/`pricing_config`
   still advertised the old deleted ~47-function surface (`show_article`, `publish_wp`, …), which made
   Webbee hallucinate nonexistent calls (one turn burned 320k tokens). Fix the portal description to
   match the real 20-function set (manual, Ignat).
3. **RichEditor has no link button** (SDK gap) — relay to SDK dev.
4. Backend open items → `article-writer-backend/PLAN.md` (not duplicated here). Backend unchanged today.
