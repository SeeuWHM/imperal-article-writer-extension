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
