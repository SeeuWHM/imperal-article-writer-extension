"""richtext.py — plain text <-> HTML round trip for the panel's RichEditor."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from richtext import to_html, from_html


def test_to_html_wraps_paragraphs():
    assert to_html("First paragraph.\n\nSecond paragraph.") == (
        "<p>First paragraph.</p><p>Second paragraph.</p>"
    )


def test_to_html_bold_and_italic():
    assert to_html("This is **bold** and *em*.") == "<p>This is <strong>bold</strong> and <em>em</em>.</p>"


def test_to_html_bullet_list():
    assert to_html("- one\n- two") == "<ul><li>one</li><li>two</li></ul>"


def test_to_html_empty():
    assert to_html("") == ""
    assert to_html(None) == ""


def test_from_html_reverses_paragraphs():
    assert from_html("<p>First paragraph.</p><p>Second paragraph.</p>") == (
        "First paragraph.\n\nSecond paragraph."
    )


def test_from_html_reverses_bold_and_italic():
    assert from_html("<p>This is <strong>bold</strong> and <em>em</em>.</p>") == "This is **bold** and *em*."


def test_from_html_reverses_bullet_list():
    assert from_html("<ul><li>one</li><li>two</li></ul>") == "- one\n- two"


def test_from_html_is_noop_on_plain_text():
    """Content saved via chat (not the panel) arrives as plain text — must
    pass through unchanged so save_article_section stays safe for both callers."""
    plain = "Just plain text with **bold** already in markdown form."
    assert from_html(plain) == plain


def test_round_trip_preserves_meaning():
    original = "Intro paragraph with **bold** text.\n\n- bullet one\n- bullet two\n\nClosing paragraph."
    assert from_html(to_html(original)) == original
