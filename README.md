# imperal-article-writer-extension

[![Imperal SDK](https://img.shields.io/badge/imperal--sdk-5.9.3-blue)](https://pypi.org/project/imperal-sdk/)
[![Version](https://img.shields.io/badge/version-2.4.0-green)](https://github.com/SeeuWHM/imperal-article-writer-extension/releases)
[![License](https://img.shields.io/badge/license-LGPL--2.1-orange)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Imperal%20Cloud-purple)](https://panel.imperal.io)

**Project-based SEO article writing extension for [Imperal Cloud](https://panel.imperal.io).**

Keep per-site context — keywords, brand voice, useful links, socials, and a list of the site's own pages available for internal linking — then have Webbee write articles grounded in that context and in real facts you give it (web search results, other extensions' data). Generation runs a full pipeline (outline → draft → mechanical gates → grounding → judge → targeted revision) on a dedicated backend microservice, never on `ctx.store`. Full article bodies are read and hand-edited in the panel's single rich-text editor at zero LLM cost; chat only ever sees metadata, unless you explicitly ask to export a body or edit it via natural language.

---

## What It Does

Talk to it naturally:

```
"create a project for webhostmost.com — keywords: managed wordpress hosting, cheap vps hosting"
"write an article about choosing a VPS plan, ground it in these facts: ..."
"rewrite the intro to be punchier"
"add this page as a reference link — it's about our uptime guarantee, so the writer can link to it"
"is my article ready yet?"
"send that article to my inbox"
```

Or use the panel — the left sidebar shows the currently-open project's full context (keywords, site URL, description) plus a compact switcher for every other project; the center workspace is a status board (idea / writing / review / published) that opens into one seamless editor per article, where the leading heading is the title and everything below it is the body.

---

## Capabilities

| Area | What it does |
|------|--------------|
| **Projects** | Create/list/update/delete a per-site context container: name, site URL, description, keywords, useful links, social links, brand voice |
| **Interlinking** | Register internal pages of the project's own site (`add_reference_link`/`list_reference_links`/`remove_reference_link`) with a topic description; the backend's writer turns them into natural, in-sentence anchors |
| **Articles** | Create an empty article shell, list by project/status, move through the `idea → writing → review → published` pipeline, fix SEO metadata (title/meta description/target keyword) without touching the body |
| **AI generation** | `generate_article` enqueues the backend's async outline → draft → grounding → judge pipeline; `check_generation_status` polls it; `patch_article` rewrites one section by instruction, synchronously |
| **Full-text editing** | `read_full_article`/`edit_full_article` — Webbee reads the whole article as Markdown and resends an edited version verbatim (nothing re-generated); `save_article_section` is a raw manual overwrite for pasted/dictated text |
| **Export** | `export_article_text` hands the full body (both HTML and plain text) to another extension — email it, save it as a note, paste it elsewhere |
| **Panel editing** | The workspace panel's single `ui.RichEditor` reads/writes the whole article directly via plain server-side HTTP calls — zero LLM tokens, any corpus size |
| **Proactive alerts** | The skeleton fires a notice the moment a generation job lands in `review`, so Webbee can tell the user their article is ready without being asked |

---

## Architecture

```
imperal-article-writer-extension/
├── main.py               # Entry point — sys.modules hot-reload cleanup + imports
├── app.py                # Extension + ChatExtension init, backend_jwt secret, health check
├── api_client.py         # call_backend(): the one HTTP client every handler/panel/skeleton uses
├── params.py             # Pydantic param models for every chat.function (mirror backend schemas)
├── response_models.py    # Pydantic response models — ArticleSummary is structurally body-free
├── richtext.py           # plain-text/light-markdown <-> HTML <-> Markdown conversion for the editor
├── navstate.py           # tiny ctx.store nav doc (view/project_id/article_id) shared by both panels
├── skeleton.py           # @ext.skeleton: project/article counts by status + proactive ready-alert
├── handlers_projects.py  # create/list/update/delete project + reference-link CRUD
├── handlers_articles.py  # article metadata CRUD, save_article_section/save_full_article, export_article_text
├── handlers_generate.py  # generate_article, check_generation_status, patch_article
├── handlers_edit.py      # read_full_article, edit_full_article — Webbee's full-text read/edit loop
├── panels_side.py        # LEFT panel "sidebar": active-project detail + compact project switcher
├── panels_workspace.py   # CENTER panel "workspace": article board + single-editor article view
├── icon.svg              # quill/feather icon
├── imperal.json          # manifest, regenerated by `imperal build`
├── pyproject.toml
└── tests/
    ├── test_handlers.py  # project/article CRUD, generation, patch — MockContext, no network
    ├── test_edit.py      # read_full_article / edit_full_article round-trip
    ├── test_richtext.py  # pure round-trip tests for markdown <-> HTML <-> plaintext
    └── test_skeleton.py  # skeleton refresh + change-alert logic
```

There is no cross-extension IPC anywhere in this codebase — this extension is a thin, honest client of one shared backend microservice (`article-writer-api`, `api.webhostmost.com/article-writer`), Galera-backed and multi-tenant by platform identity (`X-Imperal-Id`). Every backend call also carries a `backend_jwt` — a developer-managed, app-scoped secret that authenticates the extension itself, never a per-user credential.

---

## Function Reference

| Function | Type | Description |
|----------|------|--------------|
| `create_project` | write | Create a new per-site context container |
| `list_projects` | read | List all projects — id, name, site URL, keywords |
| `update_project_context` | write | Patch any project context field (name/site/description/keywords/links/brand voice) |
| `delete_project` | destructive | Delete a project and cascade-delete all its articles |
| `add_reference_link` | write | Register one internal page (url + topic description) the writer may link to |
| `list_reference_links` | read | List a project's saved reference links |
| `remove_reference_link` | destructive | Remove one reference link by URL |
| `create_article` | write | Create an empty article shell (title/keyword placeholder, no content) |
| `list_articles` | read | List article metadata, optionally filtered by project/status |
| `update_article_status` | write | Move an article between idea / writing / review / published |
| `update_article_meta` | write | Fix title/meta description/target keyword without touching the body |
| `save_article_section` | write | Raw manual overwrite of one section's heading/content — no AI, no review |
| `save_full_article` | write | Panel-only: replace the whole article from the merged editor |
| `delete_article` | destructive | Permanently delete an article |
| `export_article_text` | read | Return the full body as HTML + plain text, for handing to another extension |
| `generate_article` | write | Enqueue the backend's full generation pipeline; returns a job to poll |
| `check_generation_status` | read | Poll a generation job's status, model, tokens, cost |
| `patch_article` | write | Rewrite one section by natural-language instruction; returns a short preview |
| `read_full_article` | read | Return the entire article as editable Markdown |
| `edit_full_article` | write | Replace the entire article with an edited Markdown version, stored verbatim |

**Skeleton:** `skeleton_refresh_article_writer_overview` (project/article counts by status, TTL 60s, degrades to zeros if the backend is unreachable) and `skeleton_alert_article_writer_overview` (fires a "your article is ready" notice when the review count rises).

---

## Development

```bash
# from the SeeU-Extensions workspace root, using the shared venv
../.venv-ext/bin/python -m pytest tests/ -q   # 58 tests — MockContext + monkeypatched call_backend, no network

python3 -m py_compile *.py                    # syntax check before every commit

imperal build       # regenerate imperal.json from the live @chat.function/@ext.panel/@ext.skeleton decorators
imperal validate    # manifest schema check
```

---

## Built with

- [imperal-sdk](https://github.com/imperalcloud/imperal-sdk) 5.9.3
- [Imperal Cloud](https://panel.imperal.io)
