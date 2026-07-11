"""Newsletter editor view extracted from panels_editor."""
from __future__ import annotations

from imperal_sdk import ui

STATUS_COLOR = {
    "idea":      "gray",
    "writing":   "blue",
    "review":    "yellow",
    "published": "green",
}


def _newsletter_editor(item: dict, mode: str) -> ui.UINode:
    kw           = item.get("keyword", "")
    title        = item.get("title", "")
    subject      = item.get("subject", "")
    content_html = item.get("content", "")
    status       = item.get("status", "idea")

    nl_toggle = ui.Button(label="Preview", on_click=ui.Call("__panel__editor", active_view="editor", editor_mode="preview", note_id="board")) \
        if mode == "edit" else \
        ui.Button(label="← Edit", on_click=ui.Call("__panel__editor", active_view="editor", editor_mode="edit", note_id="board"))

    header = ui.Stack(children=[
        ui.Stack(children=[
            ui.Button(label="← Plan", on_click=ui.Call("__panel__editor", active_view="plan", note_id="board")),
            ui.Header(text=title or subject or kw, level=3),
            ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
            ui.Badge(label="newsletter", color="violet"),
        ], direction="h", gap=8),
        nl_toggle,
    ], direction="h", justify="between")

    generate_form = ui.Section(
        title="Generate newsletter from news",
        children=[
            ui.Form(
                action="generate_newsletter",
                submit_label="Generate newsletter →",
                children=[
                    ui.TextArea(
                        param_name="news_text",
                        placeholder="Paste the news, update, or topic here...",
                        rows=5,
                    ),
                    ui.Input(param_name="tone_note", placeholder="Tone note (optional)"),
                ],
            ),
        ],
    )

    if not content_html:
        return ui.Stack(children=[
            header,
            ui.Divider(),
            generate_form,
            ui.Alert(message="Enter a topic above and click Generate.", type="info"),
        ])

    if mode == "preview":
        outer = "background:#e8e8e8;padding:32px;border-radius:10px;"
        inner = (
            "max-width:620px;margin:0 auto;background:#fff;border-radius:8px;"
            "padding:40px 44px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "font-size:15px;line-height:1.75;color:#1a1a1a;"
        )
        meta_bar = f'<div style="max-width:620px;margin:0 auto 8px;font-size:12px;color:#888;"><strong>Subject:</strong> {subject or "—"}</div>'
        content_area = ui.Stack(children=[
            ui.Text(content="Email preview — copy text or switch to Edit to get raw HTML", variant="caption"),
            ui.Html(content=f'<div style="{outer}">{meta_bar}<div style="{inner}">{content_html}</div></div>'),
        ])
    else:
        content_area = ui.Form(
            action="save_draft",
            submit_label="Save",
            children=[
                ui.Input(param_name="title",   value=title,   placeholder="Title"),
                ui.Input(param_name="subject", value=subject, placeholder="Email subject line"),
                ui.RichEditor(param_name="content", content=content_html, placeholder="Newsletter body"),
            ],
        )

    status_form = ui.Form(
        action="update_status",
        submit_label="Update status",
        children=[
            ui.Select(param_name="status", placeholder=f"Status: {status}", options=[
                {"value": "idea",      "label": "Idea"},
                {"value": "writing",   "label": "Writing"},
                {"value": "review",    "label": "Review — ready to paste into MailerLite"},
                {"value": "published", "label": "Published / Sent"},
            ]),
        ],
    )

    return ui.Stack(children=[
        header,
        ui.Divider(),
        generate_form,
        ui.Divider(),
        content_area,
        ui.Divider(),
        ui.Alert(message="Ready? Copy from Preview → paste into MailerLite → schedule.", type="info"),
        status_form,
    ])
