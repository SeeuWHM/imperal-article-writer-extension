"""Plain-text/lightweight-markdown <-> HTML conversion for the panel's
RichEditor (TipTap — its `content` prop is an HTML string). The backend
stores/scores plain text with light markdown (**bold**, *em*, "- " bullets —
exactly what the generation pipeline's prompts produce), so every read goes
through to_html() and every save goes through from_html() to keep that
contract unchanged end to end.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_HTML_STRONG = re.compile(r"<(?:strong|b)>(.*?)</(?:strong|b)>", re.DOTALL)
_HTML_EM = re.compile(r"<(?:em|i)>(.*?)</(?:em|i)>", re.DOTALL)
_HTML_LIST = re.compile(r"<(ul|ol)>(.*?)</\1>", re.DOTALL)
_HTML_LI = re.compile(r"<li>(.*?)</li>", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_BLOCK = re.compile(r"<p>.*?</p>|<ul>.*?</ul>|<ol>.*?</ol>", re.DOTALL)
_HTML_HEADING = re.compile(r"<h[23]>(.*?)</h[23]>", re.DOTALL)
_HTML_HEADING_SPLIT = re.compile(r"(<h[23]>.*?</h[23]>)", re.DOTALL)


def _inline_to_html(text: str) -> str:
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return text


def to_html(text: str) -> str:
    """Section plain text -> HTML for RichEditor display."""
    if not text or not text.strip():
        return ""
    blocks = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
        if lines and all(ln.startswith(("- ", "* ")) for ln in lines):
            items = "".join(f"<li>{_inline_to_html(ln[2:])}</li>" for ln in lines)
            blocks.append(f"<ul>{items}</ul>")
        else:
            blocks.append(f"<p>{_inline_to_html(' '.join(lines))}</p>")
    return "".join(blocks)


def _unescape(text: str) -> str:
    return (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    )


def _block_to_text(block: str) -> str:
    list_match = _HTML_LIST.match(block)
    if list_match:
        items = _HTML_LI.findall(list_match.group(2))
        return "\n".join(f"- {_HTML_TAG.sub('', it).strip()}" for it in items)
    inner = re.sub(r"</?p>", "", block)
    inner = re.sub(r"<br\s*/?>", "\n", inner)
    return _HTML_TAG.sub("", inner).strip()


def from_html(html: str) -> str:
    """RichEditor HTML -> plain text with light markdown, the shape the
    backend's mechanical checks / grounding / patch pipeline expects.

    Converts inline formatting first, then splits into top-level <p>/<ul>/<ol>
    blocks and rejoins them with blank lines — this is what lets a paragraph
    sitting right next to a list round-trip correctly instead of only
    matching two adjacent <p> tags.
    """
    if not html or not html.strip():
        return ""
    text = _HTML_STRONG.sub(r"**\1**", html)
    text = _HTML_EM.sub(r"*\1*", text)

    blocks = _HTML_BLOCK.findall(text)
    if not blocks:
        # No recognizable block tags — plain text (e.g. from chat) passes through untouched.
        return _unescape(_HTML_TAG.sub("", text)).strip()

    converted = [_block_to_text(b) for b in blocks]
    return _unescape("\n\n".join(b for b in converted if b))


def sections_to_html(sections: list[dict]) -> str:
    """Merge an article's sections into ONE HTML document — the panel's
    single-window editor. Each section's heading becomes a real <h2>, so
    TipTap's own heading formatting is what carries section boundaries."""
    parts = []
    for section in sections:
        heading = (section.get("heading") or "").strip()
        if heading:
            parts.append(f"<h2>{heading}</h2>")
        parts.append(to_html(section.get("content") or ""))
    return "".join(parts)


def html_to_sections(html: str) -> list[dict]:
    """Split ONE merged document back into {heading, content} sections at
    <h2>/<h3> boundaries — the inverse of sections_to_html(). Content typed
    before the first heading (if any) becomes a heading-less first section;
    this is how a genuinely free-edited document (headings added/removed/
    reordered by the user) round-trips instead of only ever matching the
    original section count."""
    if not html or not html.strip():
        return []

    parts = _HTML_HEADING_SPLIT.split(html)
    sections: list[dict] = []
    heading: str | None = None
    body = ""
    for part in parts:
        if not part or not part.strip():
            continue
        match = _HTML_HEADING.match(part)
        if match:
            if heading is not None or body.strip():
                sections.append({"heading": heading, "content": from_html(body)})
            heading = _unescape(_HTML_TAG.sub("", match.group(1))).strip()
            body = ""
        else:
            body += part
    if heading is not None or body.strip():
        sections.append({"heading": heading, "content": from_html(body)})
    return sections
