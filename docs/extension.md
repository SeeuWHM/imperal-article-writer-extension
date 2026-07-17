# Article Writer Extension — Full Documentation

**Version:** 2.5.0 (code HEAD = prod, deployed and verified live 2026-07-18) |
**SDK:** imperal-sdk 5.9.9 | **app_id:** `imperal-article-writer-extension` | **tool_name:** `article_writer`
**Git:** `github.com/SeeuWHM/imperal-article-writer-extension`
**Backend:** `SeeU-Extensions/article-writer-backend/` (single source of truth for the backend —
schema, API surface, generation pipeline, deploy status). This doc covers the extension side only.

> **Resume point (2026-07-18).** Everything below reflects the real code at HEAD, and it is the real
> code running in prod — confirmed live via `list_projects`/`open_project` calls today, not just
> pushed-and-hoped. `capabilities` now declares `notify:push` (see "Deploy gotcha" below) — without it
> every deploy silently rolled back to the previous commit.

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
- **Webbee can read and edit the full text**: `read_full_article` returns the whole body as editable
  Markdown, `edit_full_article` replaces it verbatim from submitted Markdown. This is a deliberate
  relaxation of the "chat never sees the body" rule. The metadata list functions (`list_articles`,
  etc.) still stay body-free by design (`ArticleSummary` has no `content`/`sections` field).
- **All tool descriptions and hints are English-only** (2026-07-18 policy) — no bilingual
  `русская_фраза, english_phrase` trigger lists anywhere in a `@chat.function`/`Extension` description.
  Webbee already understands non-English input semantically; it doesn't need the literal phrase baked
  into the description to route correctly.

Out of scope (other extensions Webbee orchestrates): SE Ranking, GSC, WordPress publishing, Rank Math.

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (21) or panel action
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

Every `call_backend` failure now carries a **structured `error_code`** (SDK 5.9.9
`ActionResult.error(code=...)`), not just prose — see "Error handling" below.

---

## File structure

```
article-writer-extension/
├── main.py               — entry point; hot-reload module list (imports handlers_edit too)
├── app.py                — Extension + ChatExtension init, backend_jwt secret, health check.
│                            capabilities=[..., "notify:push"] — REQUIRED because skeleton.py calls
│                            ctx.notify(); omitting it silently rolls back every deploy attempt.
├── api_client.py         — call_backend(): the one HTTP client every handler/panel/skeleton uses.
│                            Centralizes _err() (imported by every handlers_*.py) — every error path
│                            (timeout, unreachable, 401/404/5xx) carries a structured error_code.
├── params.py             — chat-function Pydantic param models (mirror backend request schemas).
│                            EntityId type rejects obvious placeholder ids ("unknown", "null", "",
│                            "string", …) client-side before ever hitting the network.
├── response_models.py    — data_model response models (ArticleSummary is structurally body-free;
│                            ArticleFullText = export; ArticleTextRecord = read-for-edit markdown;
│                            PatchResult carries matched/replaced_count honesty fields).
├── richtext.py           — text/markdown <-> HTML (panel) AND markdown <-> document (Webbee edit):
│                            sections_to_html/html_to_sections, document_to_html/html_to_document,
│                            document_to_markdown/markdown_to_document
├── navstate.py           — tiny ctx.store nav doc (view/project_id/article_id)
├── skeleton.py           — @ext.skeleton(alert=True) refresh + paired skeleton_alert_* tool, PLUS a
│                            direct ctx.notify() call gated on our own ctx.store baseline (the
│                            reliable proactive-alert path — see "Proactivity" below)
├── handlers_projects.py  — project CRUD + reference links + open_project (sidebar-switch fix)
├── handlers_articles.py  — article CRUD, status/meta, save_section, save_full (panel), export
├── handlers_generate.py  — generate_article, patch_article
├── handlers_edit.py      — read_full_article, edit_full_article (Webbee full-text read/edit)
├── panels_side.py        — LEFT "sidebar": active-project detail + compact project switcher
├── panels_workspace.py   — CENTER "workspace": article board + single-editor article view (H1 title)
├── icon.svg · imperal.json · pyproject.toml (imperal-sdk>=5.9.9)
└── tests/  test_handlers.py · test_richtext.py · test_edit.py · test_skeleton.py · test_params.py
    (73 tests, all green)
```

Every file is under the 300-line limit.

---

## Chat-function inventory (20 functions + 2 skeleton tools)

### Projects (`handlers_projects.py`)
- `create_project(name, site_url?, description?, keywords?, useful_links?, social_links?, brand_voice?)` — write
- `list_projects()` — read, `chain_callable=True`
- `update_project_context(project_id, …any field…)` — write, ≥1 field
- `delete_project(project_id)` — destructive, cascades to articles
- `open_project(project_id)` — write, **PANEL-ONLY** [NEW 2026-07-18]. Switches the active project —
  see "Sidebar bug fix" below. Not a Webbee-facing action; pure UI navigation state.
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
- `generate_article(article_id, brief, target_keyword?, source_snippets?)` — write, enqueues async
  pipeline → `{job_id,…}`. To check when it's done, call `list_articles(status='review')` a bit
  later — an article's status lands on `review` the moment its draft is ready, so that one call shows
  everything that finished with no job_id tracking. **`check_generation_status` was removed
  (2026-07-18):** its `GET /v1/articles/{id}/jobs/{job_id}` job-poll endpoint returned an error in
  production while the direct status-list path worked, so the broken duplicate was dropped in favour
  of the one reliable path (Ignat's call).
- `patch_article(article_id, instruction, section_hint?)` — write, synchronous, one-section NL
  rewrite. **Honesty fix (2026-07-18):** `PatchResult` now carries `matched`/`replaced_count`. If the
  locate step can't find a section actually containing the instruction's target — or the edit model
  left the section byte-identical — the response is `matched=false, replaced_count=0` and **nothing
  is written**, instead of a false "Updated section" (2026-07-17 incident: a stale phone number that
  had already been removed got "replaced" in an unrelated section, and the API still said success).

### Webbee full-text read/edit (`handlers_edit.py`)
- `read_full_article(article_id)` — read. Returns the whole body as editable **Markdown**
  (`# title`, `## headings`, light-markdown body). Deliberately to chat, so Webbee edits the real text.
- `edit_full_article(article_id, content_markdown)` — write. Replaces the whole article from submitted
  Markdown, stored **verbatim** (`markdown_to_document` → sections + title via `/meta`; no
  re-generation — what Webbee sends is exactly what is stored). For a small change prefer `patch_article`.

### Skeleton (`skeleton.py`)
- `skeleton_refresh_article_writer_overview` — `alert=True`, ttl-hint 60s. Returns
  `{"response": {project_count, article_count, by_status, latest_ready, instruction}}` — flat scalars,
  counts from the paged `total`, `latest_ready` = title of the newest article in `review`. **Also**
  fires a direct `ctx.notify()` when the review count rises against our own persisted baseline — see
  "Proactivity" below.
- `skeleton_alert_article_writer_overview(ctx, old, new)` — the kernel's own old/new diff mechanism.
  Kept as a harmless second layer (mirrors mail-client's `mail_inbox_summary` pattern) but not relied
  on — see "Proactivity."

---

## Panels

- **`sidebar`** (left) — full context only for the project currently open (via `navstate`); every other
  project is a compact clickable row inside a real `ui.List` (a bare `ui.ListItem` as a direct Stack
  child once made the whole sidebar vanish — always wrap ListItem in a List). Minimal "+ New project" form.
  **Project rows route through `open_project` (a chat.function), never a raw `ui.Call("__panel__workspace", ...)`**
  — see "Sidebar bug fix" below.
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

## Sidebar bug fix (2026-07-18) — panel clicks vs. chat.function calls

**Symptom:** clicking a different project in the sidebar updated the workspace board, but the sidebar
itself kept showing the *previous* project's expanded detail (keywords, brand voice) until a full
page reload.

**Root cause:** `_project_list_item`'s `on_click` called `ui.Call("__panel__workspace", view="articles",
project_id=p["id"])` directly. A plain panel-to-panel `ui.Call` only ever refreshes the ONE panel it
targets (confirmed against the SDK's `@ext.panel` wrapper — it returns `{"ui": ..., "panel_id": ...}`,
no room for a side-channel "also refresh this other panel" signal). The sidebar had no trigger to
re-render on project switch.

**Fix:** the click now calls `open_project` — a real `@chat.function` with
`refresh_panels=["sidebar", "workspace"]`, the same mechanism `delete_article`/`delete_project` already
use successfully. `open_project` also explicitly resets `article_id` to `""` on switch — the nav-state
fields are never left to "whatever the previous call happened to carry."

---

## Proactivity (2026-07-18 — investigated and hardened)

**"Article ready" notifications ship TWO ways now:**

1. **Direct `ctx.notify()` (the reliable path).** `skeleton_refresh_article_writer_overview` persists
   its own "last-seen review count" in `ctx.store` (`article_writer_notify_state` collection) and
   calls `ctx.notify(...)` directly whenever that count rises against the count it saved last time.
   This survives *any* kernel-side workflow respawn, because the baseline lives in our own durable
   storage, not in a Temporal workflow's in-memory state.
2. **`skeleton_alert_article_writer_overview` (the kernel's own diff mechanism, kept as a harmless
   second layer)** — the platform's `IcnliSkeletonWorkflow` compares the previous skeleton snapshot to
   the new one and calls this tool when `review` count rises.

**Why #2 alone wasn't reliable (root cause, traced into the kernel source 2026-07-18):** the comparison
baseline (`_previous_data`) lives *only* in the `IcnliSkeletonWorkflow` Temporal workflow instance's
memory. It correctly survives the workflow's *own* periodic self-rotation (`continue_as_new` — the
kernel devs explicitly carry `_previous_data` forward there). It does **not** survive the *parent*
session workflow's own periodic rotation, which kills the skeleton child
(`parent_close_policy=ParentClosePolicy.TERMINATE`) and respawns a fresh one on the next message —
`workflows/session/skeleton_watchdog.py`'s `_spawn()` never passes `previous_data` forward on that
path. If a generation finishes while that respawn happens to occur, the newly-spawned workflow sees
the already-changed state on its first tick with nothing to compare against — the kernel's own alert
is silently skipped, no error logged. This is a kernel-level gap (not fixable from extension code);
path #1 above sidesteps it entirely by never depending on that in-memory baseline.

**Deploy gotcha:** adding `ctx.notify()` requires declaring `"notify:push"` in
`Extension(capabilities=[...])`. Missing it doesn't produce a soft warning — the platform's deploy
validator (`I-NOTIFY-APP-ATTRIBUTED`) rejects the deploy outright and silently rolls back to the
previous commit. Confirmed live 2026-07-18 (this is why the fix took two commits: the notify code,
then the missing capability).

**Proactive source data** (unchanged): the chat description tells Webbee to proactively gather the
real facts an article needs (prices, stats, specs, quotes) and pass them as `source_snippets` to
`generate_article` (so claims are grounded, nothing invented), and to collect the site's own pages as
`reference_links`. ⚠️ **Article Writer has NO fill-category store** — that mechanism (reusable items
with condition notes) exists only in Newsletter Writer.

---

## Error handling (2026-07-18)

Every `call_backend()` failure now carries a structured `error_code` (SDK 5.9.9
`ActionResult.error(code=...)`) instead of bare prose:

| Situation | `error_code` | `retryable` |
|---|---|---|
| Backend URL/JWT not configured | `BACKEND_NOT_CONFIGURED` | false |
| Backend timed out | `BACKEND_TIMEOUT` | true |
| Backend unreachable (connection error) | `BACKEND_5XX` | true |
| 401 from backend | `PERMISSION_DENIED` | false |
| 404 from backend | `NOT_FOUND` | false |
| Backend 5xx | `BACKEND_5XX` | true |
| Backend other 4xx | `BACKEND_REJECTED` | false |
| Client-side "nothing to update/save" | `VALIDATION_MISSING_FIELD` | false |
| Placeholder-looking id (`"unknown"`, `""`, …) | Pydantic `ValidationError` at the arg gate, before any network call | — |

`_err()` lives once in `api_client.py` now (every `handlers_*.py` imports it) — previously each file
had its own copy that only ever built a code-less error.

---

## Secrets — EXT-SECRETS-V1, one secret

`ext.secret(name="backend_jwt", required=True, scope="app", env_fallback="IMPERAL_APPSECRET_ARTICLE_WRITER_BACKEND_JWT", max_bytes=2048)`.
Developer-set only. No per-user secret exists.

---

## Cyrillic strip (2026-07-18)

Every `@chat.function`/`Extension`/`ChatExtension` description used to carry bilingual
`"Use for: русская фраза, english phrase"` trigger lists. Per policy, all of these are now
**English-only** — the Russian phrases were removed, the English ones kept, punctuation cleaned up.
This does not reduce Russian-language usability: Webbee already understands non-English chat input
semantically without needing the literal phrase baked into a tool's description.

---

## Pricing (per_action) — current + recommendation

Prices are "tokens/credits per function call". Reality: only `generate_*` (multi-LLM pipeline) and
`patch_*` (2 LLM calls) spend backend LLM tokens; `read_full`/`edit_full`/`export` spend Webbee
context tokens ∝ body size; everything else is cheap DB. Frequently-called list/check functions must
stay cheapest.

Current AW prices and my suggested adjustments:
- `list_*` = 10 ✓ (called constantly — including as the generation-done check — keep cheapest)
- `create/update/delete/status/meta`, reference-link ops = 10–30 ✓
- `open_project` [NEW] → **0/free** — pure UI navigation, no LLM, no meaningful backend cost (one
  cheap GET); matches the "PANEL-ONLY" functions' free-tier intent below
- `save_article_section`, `save_full_article` (PANEL, 0 LLM) = 20 → **consider 0/min** (panel edit was meant free)
- `read_full_article` = 200 → **120–150** (don't discourage the read Webbee now needs)
- `edit_full_article` = 100 → **≥ read** (editing outputs the whole body — costs more than reading it)
- `export_article_text` = 60 → **≥ read** (returns 2 copies text+html — shouldn't be cheaper than read)
- `patch_article` = 50 ✓
- `generate_article` = 800 ✓ (correct anchor — the heaviest op)

A typical edit cycle = `read_full` + `edit_full`, so the user pays for both — keep each moderate.

---

## Tests

73 tests (`../.venv-ext/bin/pytest tests/ -q`):
- `test_handlers.py` — project/article CRUD, generate/patch, title-in-editor save, body-free
  guarantees, **`open_project` refreshes both panels + resets `article_id`**
- `test_richtext.py` — HTML + document + markdown round-trips, H1-title extraction
- `test_edit.py` — read_full/edit_full read+persist, empty-input guard
- `test_skeleton.py` — change-alert logic, **plus the new direct `ctx.notify()` path**: fires when
  review count rises against the persisted baseline, seeds silently on first-ever run (no persisted
  doc yet — nothing "just finished," no false alert), never re-notifies when the count is unchanged
- `test_params.py` — placeholder ids (`"unknown"`, `""`, …) rejected before any network call

---

## Open items

1. **RichEditor has no link button** (SDK gap) — relay to SDK dev.
2. **Dev Portal app registration** — verify `display_name`/`description`/`pricing_config` in the
   marketplace listing match the real 21-function surface (a stale listing previously advertised a
   deleted ~47-function surface and made Webbee hallucinate nonexistent calls).
3. Backend open items → `article-writer-backend/PLAN.md` (not duplicated here). Backend's own
   `patch.py`/`locate.py`/`llm_client.py` got the matching honesty fix (locate sees section content,
   can return "no match," a byte-identical edit is also treated as no-op) — deployed to api-server
   2026-07-17/18, covered by its own test suite there.
