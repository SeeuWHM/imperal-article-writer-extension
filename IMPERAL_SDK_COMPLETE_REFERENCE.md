# Imperal SDK Complete Reference Documentation

**Version:** 3.5.0 (as of 2026-04-30)  
**Last Updated:** 2026-04-30  
**SDK Package:** `imperal-sdk>=3.0.0,<4.0.0`

---

## TABLE OF CONTENTS

1. [Quick Facts](#quick-facts)
2. [Extension Architecture](#extension-architecture)
3. [Panel System & UI](#panel-system--ui)
4. [UI Components (57 Total)](#ui-components-57-total)
5. [Chat Functions & Decorators](#chat-functions--decorators)
6. [Context Object & APIs](#context-object--apis)
7. [Store API (Document Storage)](#store-api-document-storage)
8. [HTTP API](#http-api)
9. [AI API](#ai-api)
10. [Event System](#event-system)
11. [Navigation Patterns](#navigation-patterns)
12. [Known Limitations & Broken Components](#known-limitations--broken-components)
13. [Complete File Structure](#complete-file-structure)
14. [Testing with MockContext](#testing-with-mockcontext)

---

## QUICK FACTS

- **Imperal:** AI Cloud Operating System ("Shopify for AI agents")
- **Primary Pattern:** Single `ChatExtension` entry point per extension
- **LLM Integration:** BYOLLM (bring your own LLM) with multi-model routing
- **Panel Layout:** 3-column standardized (left sidebar, center chat, right panel)
- **Valid Slots:** `center`, `left`, `right`, `overlay`, `bottom`, `chat-sidebar` only
- **UI Framework:** 57 declarative components, zero React, Tailwind-managed by platform
- **Validation Requirement:** 80% line coverage for CI deployment
- **Default Timeout:** 60 seconds per tool (configurable)
- **Token Budget:** Automatic trimming; extensions return large data freely

---

## EXTENSION ARCHITECTURE

### Single-Entry-Point Golden Rule

**Every extension MUST have exactly ONE user-facing `ChatExtension` tool.**

```python
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult

ext = Extension("my-extension", version="1.0.0")
chat_ext = ChatExtension(
    ext=ext,
    tool_name="tool_my_extension_chat",
    description="Main entry point for AI routing"
)
```

**Why?**
- Ensures proper discovery and embedding-based routing
- Prevents tool fragmentation
- Centralizes LLM intent routing
- Enforces ICNLI integrity rules

### File Structure (Mandatory v1.0+)

```
extension/
├── main.py              # Entry point - MUST clean sys.modules
├── app.py               # ext, chat_ext, system prompt, @ext.health_check
├── handlers.py          # @chat.function decorators (max 300 lines)
├── handlers_*.py        # Split additional handlers
├── skeleton.py          # @ext.skeleton tools (optional)
├── requirements.txt     # Dependencies
└── tests/
    └── test_*.py        # Unit tests (80% coverage minimum)
```

---

## PANEL SYSTEM & UI

### The Three-Column Layout

Imperal enforces a **standardized 3-column layout**:

- **Left Sidebar** (`slot="left"`): Navigation, item lists
- **Center** (`slot="center"`): Main content, AI chat
- **Right Panel** (`slot="right"`): Detail panes, context

**CRITICAL:** Only these 6 slot values are valid:
- `"center"`, `"left"`, `"right"`, `"overlay"`, `"bottom"`, `"chat-sidebar"`

Using `slot="main"` raises `ValueError` (v3.4.0+).

### Master-Detail Pattern (Most Common)

Left sidebar list + center panel updates via `ui.Call()`.

---

## UI COMPONENTS (57 TOTAL)

### Layout Components (8)
`ui.Stack`, `ui.Grid`, `ui.Tabs`, `ui.Page`, `ui.Section`, `ui.Row`, `ui.Column`, `ui.Accordion`

### Display Components (9)
`ui.Text`, `ui.Header`, `ui.Icon`, `ui.Image`, `ui.Code`, `ui.Markdown`, `ui.Divider`, `ui.Empty`, `ui.Html`

### Interactive Components (7)
`ui.Button`, `ui.Card`, `ui.Menu`, `ui.Dialog`, `ui.Tooltip`, `ui.Link`, `ui.SlideOver`

### Input Components (11)
`ui.Input`, `ui.TextArea`, `ui.Toggle`, `ui.Select`, `ui.MultiSelect`, `ui.Slider`, `ui.DatePicker`, `ui.FileUpload`, `ui.Form`, `ui.RichEditor`, `ui.TagInput`

**Form Pattern:** All inputs with `param_name` register automatically, including unchanged fields.

### Data Display Components (11)
`ui.List`, `ui.ListItem`, `ui.DataTable`, `ui.DataColumn`, `ui.Stat`, `ui.Stats`, `ui.Badge`, `ui.Avatar`, `ui.Timeline`, `ui.Tree`, `ui.KeyValue`

### Visualization (1)
`ui.Graph` (Cytoscape, max ~5,000 nodes)

### Feedback Components (5)
`ui.Alert`, `ui.Progress`, `ui.Chart`, `ui.Loading`, `ui.Error`

### Actions (Non-Visual)
`ui.Call(function, **params)`, `ui.Navigate(path)`, `ui.Send(message)`, `ui.Open(url)`

---

## CHAT FUNCTIONS & DECORATORS

### `@chat.function` (Production Pattern)

```python
@chat_ext.function(
    name="create_note",
    description="Create a new note",
    action_type="write",
    event="created"
)
async def fn_create_note(self, title: str):
    doc = await self.ctx.store.create("notes", {"title": title})
    return ActionResult.success(
        data={"note_id": doc.id},
        summary=f"Note '{title}' created"
    )
```

**Parameters:**
- `name`: Function identifier
- `description`: What it does (for LLM)
- `action_type`: `"read"`, `"write"`, or `"destructive"`
- `event`: Automation trigger event name

**Return:** `ActionResult` (mandatory)

### Lifecycle Decorators

- `@ext.signal(event_type)` — Platform events
- `@ext.schedule(cron="...")` — Background tasks
- `@ext.health_check` — Status monitoring
- `@ext.on_event(event_type)` — Event subscription
- `@ext.webhook(path="/...")` — External HTTP
- `@ext.on_install` / `@ext.on_upgrade()` — Lifecycle
- `@ext.skeleton("name", ttl=300)` — AI-visible context (LLM-only)

---

## CONTEXT OBJECT & APIs

Automatically injected; never construct manually.

### `ctx.store` — Document Storage
```python
await ctx.store.create("notes", {"title": "..."})
await ctx.store.get("notes", doc_id)
await ctx.store.query("notes", where={"archived": False}, limit=10)
await ctx.store.update("notes", doc_id, {"title": "..."})
await ctx.store.delete("notes", doc_id)
```

### `ctx.http` — External API Calls
```python
response = await ctx.http.get("https://api.example.com/...", headers={...})
await ctx.http.post(url, json={...})
await ctx.http.put/patch/delete(url, ...)
```

**Rate limit:** 100 req/min; timeout: 30s default

### `ctx.ai` — LLM Completion
```python
result = await ctx.ai.complete(prompt="...", model="claude-3.5-sonnet")
result = await ctx.ai.chat(messages=[...], model="gpt-4o")
# Returns: CompletionResult with .text, .usage
```

### `ctx.notify` — Notifications
```python
await ctx.notify("Message text", priority="high", channels=["in_app", "email"])
```

### `ctx.skeleton` — AI-Visible Context (v1.6.0+)
**CRITICAL:** Accessible ONLY in `@ext.skeleton` tools. Raises `SkeletonAccessForbidden` elsewhere.
```python
prev = await ctx.skeleton.get("section_name")  # Legal in @ext.skeleton only
# Update via return value; .update() method removed
```

### `ctx.cache` — Panel Runtime Cache (5-300s TTL, 64 KB)
```python
cached = await ctx.cache.get("key")
await ctx.cache.set("key", value, ttl=300)
result = await ctx.cache.get_or_fetch("key", lambda: fetch_data(), ttl=300)
```

### `ctx.config` — Configuration
```python
value = await ctx.config.get("setting.name")
section = await ctx.config.get_section("section")
all_config = await ctx.config.all()
```

### `ctx.user` — User Identity & Permissions
```python
ctx.user.id / ctx.user.imperal_id
ctx.user.email
ctx.user.tenant_id
ctx.user.scopes
ctx.user.has_scope("notes:write")
ctx.user.can("notes:read", {"department": "engineering"})  # ABAC
```

### `ctx.billing` — Usage Limits
```python
limits = await ctx.billing.check_limits()
subscription = await ctx.billing.get_subscription()
balance = await ctx.billing.get_balance()
```

### `ctx.storage` — Binary File Storage
```python
url = await ctx.storage.upload("filename.pdf", file_bytes)
data = await ctx.storage.download("filename.pdf")
await ctx.storage.delete("filename.pdf")
```

### `ctx.extensions` — Inter-Extension IPC
```python
result = await ctx.extensions.call("other_extension", "function_name", param="value")
await ctx.extensions.emit("event_type", {"data": "..."})
```

### `ctx.time` — Timezone & Time Data
```python
ctx.time.timezone
ctx.time.utc_offset
ctx.time.now_utc / now_local
ctx.time.hour_local
ctx.time.is_business_hours
```

---

## STORE API (DOCUMENT STORAGE)

Auto-provisioned per-tenant, no setup required.

```python
# CREATE
doc = await ctx.store.create("notes", {"title": "...", "body": "..."})

# GET
note = await ctx.store.get("notes", doc_id)

# QUERY with filtering
results = await ctx.store.query(
    "notes",
    where={"title": {"$contains": "urgent"}},
    limit=10,
    offset=0,
    sort=[("created_at", "desc")]
)
# Returns: Page[dict] with .items and .total

# COUNT
count = await ctx.store.count("notes", where={"archived": False})

# UPDATE (partial)
updated = await ctx.store.update("notes", doc_id, {"title": "New Title"})

# DELETE (soft delete)
await ctx.store.delete("notes", doc_id)

# QUERY ALL (auto-pagination)
all_notes = await ctx.store.query_all("notes", where={"archived": False})
```

---

## EVENT SYSTEM

### Publishing

Write/destructive functions auto-publish on success:

```python
@chat_ext.function("send_email", action_type="write", event="sent")
async def fn_send_email(self, to: str):
    return ActionResult.success(
        data={"email_id": "123", "to": to},
        summary="Email sent"
    )
    # Auto-publishes: {app_id}.sent event with data
```

### Subscription

```python
@ext.on_event("notes.created")
async def on_note_created(ctx, data):
    await ctx.notify(f"New note: {data['title']}")
```

---

## KNOWN LIMITATIONS

- **Skeleton Access (v1.6.0+):** Forbidden outside `@ext.skeleton` tools; raises `SkeletonAccessForbidden`
- **Panel Slots (v3.4.0+):** `slot="main"` raises error; only 6 valid values
- **Skeleton `.update()`:** Method removed; use return value from skeleton tool
- **Graph Component:** Max ~5,000 nodes (Cytoscape)
- **LLM Config (v3.3.0+):** `ChatExtension(model=...)` parameter removed

---

## TESTING

```python
from imperal_sdk.testing import MockContext

ctx = MockContext(user_id="test", role="admin", language="en")

# Mock store
await ctx.store.create("notes", {"title": "Test"})

# Mock AI
ctx.ai.complete(prompt="...", model="gpt-4")

# Mock notifications
await ctx.notify("Test")
assert ctx.notify.messages[-1] == "Test"

# Test with 80% coverage minimum
imperal test tests/ --cov
```

---

## VALIDATION

Run `imperal validate` before publishing:

✓ Exactly one `ChatExtension`
✓ All handlers return `ActionResult`
✓ Pydantic params
✓ Write/destructive declare `event=`
✓ ID field names match
✓ No hardcoded secrets
✓ main.py cleans sys.modules
✓ 80% coverage

---

## DEPLOYMENT

```bash
imperal init my-ext --template chat
pip install -r requirements.txt
imperal test tests/
imperal validate
imperal deploy
imperal logs
```

---

**Document Version:** 1.0
**SDK Version:** 3.5.0
**Date:** 2026-04-30
