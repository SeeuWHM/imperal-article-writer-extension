"""richtext.py — plain text <-> HTML round trip for the panel's RichEditor."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from richtext import to_html, from_html, sections_to_html, html_to_sections


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


def test_sections_to_html_merges_headings_and_bodies():
    sections = [
        {"heading": "Intro", "content": "First paragraph."},
        {"heading": "Details", "content": "Second paragraph with **bold**."},
    ]
    assert sections_to_html(sections) == (
        "<h2>Intro</h2><p>First paragraph.</p>"
        "<h2>Details</h2><p>Second paragraph with <strong>bold</strong>.</p>"
    )


def test_html_to_sections_splits_on_headings():
    merged = "<h2>Intro</h2><p>First paragraph.</p><h2>Details</h2><p>Second paragraph.</p>"
    assert html_to_sections(merged) == [
        {"heading": "Intro", "content": "First paragraph."},
        {"heading": "Details", "content": "Second paragraph."},
    ]


def test_html_to_sections_handles_leading_content_with_no_heading():
    merged = "<p>No heading yet.</p><h2>Real section</h2><p>Body.</p>"
    assert html_to_sections(merged) == [
        {"heading": None, "content": "No heading yet."},
        {"heading": "Real section", "content": "Body."},
    ]


def test_html_to_sections_empty():
    assert html_to_sections("") == []
    assert html_to_sections("   ") == []


def test_sections_round_trip():
    sections = [
        {"heading": "Intro", "content": "Opening line.\n\n- point one\n- point two"},
        {"heading": "Conclusion", "content": "Closing thought with **emphasis**."},
    ]
    assert html_to_sections(sections_to_html(sections)) == sections


def test_to_html_converts_markdown_links():
    assert to_html("See [our pricing page](https://example.com/pricing) for details.") == (
        '<p>See <a href="https://example.com/pricing">our pricing page</a> for details.</p>'
    )


def test_from_html_reverses_links():
    assert from_html('<p>See <a href="https://example.com/pricing">our pricing page</a> for details.</p>') == (
        "See [our pricing page](https://example.com/pricing) for details."
    )


def test_link_round_trip():
    original = "Read the [full guide](https://example.com/guide) before you start."
    assert from_html(to_html(original)) == original


def test_to_html_merges_bullets_separated_by_blank_lines():
    """The draft pipeline sometimes puts a blank line between each '- ' item —
    real content seen in production. Each one must NOT become its own
    single-item <ul>; they belong in one list."""
    text = "- WooCommerce and online stores.\n\n- High-traffic sites.\n\n- Simultaneous visitors."
    assert to_html(text) == (
        "<ul><li>WooCommerce and online stores.</li>"
        "<li>High-traffic sites.</li>"
        "<li>Simultaneous visitors.</li></ul>"
    )


def test_to_html_still_splits_genuine_paragraphs_around_a_list():
    text = "Intro paragraph.\n\n- one\n\n- two\n\nClosing paragraph."
    assert to_html(text) == (
        "<p>Intro paragraph.</p><ul><li>one</li><li>two</li></ul><p>Closing paragraph.</p>"
    )


def test_html_to_sections_accepts_h1_and_h3_as_boundaries():
    """The editor's toolbar offers H1/H2/H3 — any of them must start a new
    section, not just H2 (which is only what sections_to_html re-emits)."""
    merged = "<h1>Big Heading</h1><p>Body one.</p><h3>Small heading</h3><p>Body two.</p>"
    assert html_to_sections(merged) == [
        {"heading": "Big Heading", "content": "Body one."},
        {"heading": "Small heading", "content": "Body two."},
    ]


