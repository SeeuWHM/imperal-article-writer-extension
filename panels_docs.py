"""Knowledge base panel — upload, view, delete brand documentation files."""
from __future__ import annotations

from imperal_sdk import ui

from handlers_docs import _load_docs

REFRESH = "on_event:seo.docs.updated"

ONBOARDING_PROMPT = """\
You are helping me create a brand documentation file I'll upload to my AI content assistant.
Please ask me the questions below one at a time, then compile ALL my answers into a single
well-structured Markdown (.md) file I can save and upload.

Questions to ask:
1. What is your company name?
2. What does your company do? (1-2 sentences, plain language)
3. Who is your target audience? (roles, company size, tech level)
4. Describe your brand voice. (e.g. "direct and bold, like a founder talking to users", "friendly expert, no jargon")
5. What are your top 3 differentiators vs typical competitors?
6. List your main products/plans with a one-line description each.
7. What are the most common customer objections, and how do you handle them?
8. What is your standard call-to-action text? (e.g. "Start your free trial")
9. What are your key URLs? (website, blog, Telegram, community)
10. What topics, keywords, or themes should we focus content on?

After I answer all questions, output a clean Markdown file with sections:
# Brand Documentation
## About
## Audience
## Voice & Tone
## Differentiators
## Products
## Objections & Responses
## CTAs & Links
## Content Themes
""".strip()


async def _docs_view(ctx, docs: list[dict]) -> ui.UINode:
    prompt_section = ui.Section(
        title="Step 1 — Generate your brand docs with AI",
        collapsible=True,
        children=[
            ui.Text(
                content=(
                    "Don't have a brand doc yet? Copy the prompt below, "
                    "paste it into Claude or ChatGPT, answer the questions, "
                    "then save the output as a .md file and upload it here."
                ),
                variant="caption",
            ),
            ui.Code(
                content=ONBOARDING_PROMPT,
                language="markdown",
            ),
        ],
    )

    upload_section = ui.Section(
        title="Step 2 — Upload documentation (.md or .txt)",
        children=[
            ui.Text(
                content="Uploaded docs are injected into AI prompts when writing newsletters and blog posts.",
                variant="caption",
            ),
            ui.FileUpload(
                accept=".md,.txt,.markdown",
                multiple=True,
                on_upload=ui.Call("upload_doc"),
            ),
        ],
    )

    if not docs:
        doc_list = ui.Alert(
            message="No docs uploaded yet. Use the steps above to create and upload your first brand document.",
            type="info",
        )
    else:
        doc_rows = []
        for doc in docs:
            doc_rows.append(
                ui.Stack(
                    children=[
                        ui.Stack(children=[
                            ui.Text(content=doc.get("name", "—"), variant="body"),
                            ui.Text(
                                content=f"{doc.get('size', 0):,} chars · .{doc.get('ext', 'md')}",
                                variant="caption",
                            ),
                        ]),
                        ui.Form(
                            action="delete_doc",
                            submit_label="Delete",
                            children=[ui.Input(param_name="doc_id", value=doc["id"])],
                        ),
                    ],
                    direction="h",
                    justify="between",
                )
            )

        doc_list = ui.Stack(children=[
            ui.Header(text=f"Uploaded docs ({len(docs)})", level=5),
            *doc_rows,
        ])

    return ui.Stack(children=[
        ui.Stack(children=[
            ui.Header(text="Knowledge Base", level=3),
            ui.Form(action="go_plan", submit_label="← Back", children=[]),
        ], direction="h", justify="between"),
        ui.Alert(
            message="Docs give the AI context about your brand, products, and voice — making every generated piece sound like you.",
            type="info",
        ),
        prompt_section,
        upload_section,
        ui.Divider(),
        doc_list,
    ])
