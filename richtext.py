"""Plain-text/lightweight-markdown <-> HTML conversion for the panel's
RichEditor (TipTap — its `content` prop is an HTML string). The backend
stores/scores plain text with light markdown (**bold**, *em*, "- " bullets,
"[text](url)" links — exactly what the generation pipeline's prompts
produce), so every read goes through to_html() and every save goes through
from_html() to keep that contract unchanged end to end.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_LINK_MD = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HTML_STRONG = re.compile(r"<(?:strong|b)>(.*?)</(?:strong|b)>", re.DOTALL)
_HTML_EM = re.compile(r"<(?:em|i)>(.*?)</(?:em|i)>", re.DOTALL)
_HTML_LINK = re.compile(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_HTML_LIST = re.compile(r"<(ul|ol)>(.*?)</\1>", re.DOTALL)
_HTML_LI = re.compile(r"<li>(.*?)</li>", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_BLOCK = re.compile(r"<p>.*?</p>|<ul>.*?</ul>|<ol>.*?</ol>", re.DOTALL)
# h1/h2/h3 all count as section boundaries — the editor's toolbar offers all
# three and there's no reason to silently swallow an H1/H3 heading into the
# previous section's body just because a section boundary was normalized to
# h2 on the way in. Heading *level* itself isn't stored (schema only has a
# plain-text `heading` column) — sections_to_html always re-emits h2.
_HTML_HEADING = re.compile(r"<h[123]>(.*?)</h[123]>", re.DOTALL)
_HTML_HEADING_SPLIT = re.compile(r"(<h[123]>.*?</h[123]>)", re.DOTALL)


def _inline_to_html(text: str) -> str:
    text = _LINK_MD.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return text


def to_html(text: str) -> str:
    """Section plain text -> HTML for RichEditor display.

    Adjacent all-bullet blocks get merged into ONE <ul> even when the source
    put a blank line between each "- " item (each would otherwise split()
    into its own single-item paragraph and render as a separate one-item
    list) — genuine prose paragraphs still stay split on blank lines.
    """
    if not text or not text.strip():
        return ""

    grouped: list[tuple[bool, list[str]]] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
        is_bullets = bool(lines) and all(ln.startswith(("- ", "* ")) for ln in lines)
        if is_bullets and grouped and grouped[-1][0]:
            grouped[-1][1].extend(lines)
        else:
            grouped.append((is_bullets, lines))

    blocks = []
    for is_bullets, lines in grouped:
        if is_bullets:
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
    text = _HTML_LINK.sub(lambda m: f"[{_HTML_TAG.sub('', m.group(2))}]({m.group(1)})", html)
    text = _HTML_STRONG.sub(r"**\1**", text)
    text = _HTML_EM.sub(r"*\1*", text)

    blocks = _HTML_BLOCK.findall(text)
    if not blocks:
        # No recognizable block tags — plain text (e.g. from chat) passes through untouched.
        return _unescape(_HTML_TAG.sub("", text)).strip()

    converted = [_block_to_text(b) for b in blocks]
    return _unescape("\n\n".join(b for b in converted if b))


def to_export_text(sections: list[dict]) -> str:
    """Plain-text export — kept alongside sections_to_html() for
    export_article_text (see response_models.ArticleFullText's docstring
    for why both fields are required, not just html). Strips markdown
    syntax rather than show literal ** and - as clutter; a heading gets a
    plain-text-legible treatment (upper-case + underline) instead of
    trying to fake bold."""
    parts = []
    for section in sections:
        heading = (section.get("heading") or "").strip()
        if heading:
            parts.append(f"{heading.upper()}\n{'-' * len(heading)}")
        content = section.get("content") or ""
        content = _BOLD.sub(r"\1", content)
        content = _ITALIC.sub(r"\1", content)
        content = re.sub(r"(?m)^[-*] ", "• ", content)  # "- item" -> "• item"
        if content:
            parts.append(content)
    return "\n\n".join(parts)


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
    <h1>/<h2>/<h3> boundaries — the inverse of sections_to_html(). Content typed
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
