"""HTML rendering helpers for the editor panel (brief + article preview)."""
from __future__ import annotations

import re


def _md_to_html(text: str) -> str:
    """Minimal markdown→HTML using only stdlib re. Handles brief content."""
    lines = text.split('\n')
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            lvl = len(m.group(1))
            content = _inline(m.group(2))
            out.append(f'<h{lvl}>{content}</h{lvl}>')
            i += 1; continue
        if re.match(r'^-{3,}$', line.strip()):
            out.append('<hr>')
            i += 1; continue
        if '|' in line and i + 1 < len(lines) and re.match(r'^\|[-| :]+\|', lines[i + 1]):
            cells = [c.strip() for c in line.strip('|').split('|')]
            out.append('<table><tr>' + ''.join(f'<th>{_inline(c)}</th>' for c in cells) + '</tr>')
            i += 2
            while i < len(lines) and '|' in lines[i]:
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                out.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in cells) + '</tr>')
                i += 1
            out.append('</table>')
            continue
        m = re.match(r'^[-*]\s+(.*)', line)
        if m:
            out.append(f'<li>{_inline(m.group(1))}</li>')
            i += 1; continue
        if line.strip() == '':
            out.append('')
            i += 1; continue
        out.append(f'<p>{_inline(line)}</p>')
        i += 1
    return '\n'.join(out)


def _inline(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


_BRIEF_CSS = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         font-size: 14px; line-height: 1.6; color: #e2e8f0;
         background: transparent; margin: 0; padding: 8px 12px; }
  h1 { font-size: 18px; font-weight: 700; color: #f8fafc; margin: 16px 0 8px; }
  h2 { font-size: 15px; font-weight: 600; color: #cbd5e1; margin: 14px 0 6px; border-bottom: 1px solid #334155; padding-bottom: 4px; }
  h3 { font-size: 13px; font-weight: 600; color: #94a3b8; margin: 10px 0 4px; }
  p  { margin: 6px 0; }
  ul, ol { margin: 6px 0; padding-left: 20px; }
  li { margin: 3px 0; }
  strong { color: #f1f5f9; }
  em { color: #a5b4fc; }
  hr { border: none; border-top: 1px solid #334155; margin: 12px 0; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
  th { background: #1e293b; color: #94a3b8; font-weight: 600;
       padding: 6px 10px; text-align: left; border: 1px solid #334155; }
  td { padding: 5px 10px; border: 1px solid #1e293b; color: #cbd5e1; }
  tr:nth-child(even) td { background: #0f172a20; }
  code { background: #1e293b; color: #7dd3fc; padding: 1px 5px;
         border-radius: 3px; font-size: 12px; }
  blockquote { border-left: 3px solid #334155; margin: 8px 0;
               padding: 4px 12px; color: #94a3b8; font-style: italic; }
</style>
"""

_ARTICLE_CSS = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         font-size: 16px; line-height: 1.8; color: #1e293b;
         background: #fff; margin: 0; padding: 16px 20px; }
  h1 { font-size: 26px; font-weight: 800; color: #0f172a; margin: 0 0 16px; line-height: 1.25; }
  h2 { font-size: 20px; font-weight: 700; color: #0f172a; margin: 28px 0 10px;
       border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }
  h3 { font-size: 17px; font-weight: 600; color: #1e293b; margin: 20px 0 6px; }
  h4 { font-size: 15px; font-weight: 600; color: #334155; margin: 14px 0 4px; }
  p  { margin: 0 0 14px; }
  ul, ol { margin: 0 0 14px; padding-left: 24px; }
  li { margin: 4px 0; }
  strong { color: #0f172a; }
  em { color: #475569; }
  a  { color: #2563eb; text-decoration: none; }
  hr { border: none; border-top: 2px solid #e2e8f0; margin: 24px 0; }
  table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }
  th { background: #f1f5f9; color: #334155; font-weight: 700;
       padding: 8px 12px; text-align: left; border: 1px solid #cbd5e1; }
  td { padding: 7px 12px; border: 1px solid #e2e8f0; }
  tr:nth-child(even) td { background: #f8fafc; }
  code { background: #f1f5f9; color: #0f172a; padding: 2px 6px;
         border-radius: 4px; font-size: 13px; font-family: monospace; }
  pre  { background: #f1f5f9; padding: 14px; border-radius: 8px; overflow-x: auto; }
  blockquote { border-left: 4px solid #2563eb; margin: 16px 0;
               padding: 8px 16px; color: #475569; font-style: italic;
               background: #f8fafc; border-radius: 0 6px 6px 0; }
  img { max-width: 100%; height: auto; border-radius: 6px; }
  .schema-faq-section { background: #f8fafc; border: 1px solid #e2e8f0;
                        border-radius: 8px; padding: 16px; margin: 20px 0; }
</style>
"""


def _brief_html(md_text: str) -> str:
    body = _md_to_html(md_text)
    return f"<!DOCTYPE html><html><head>{_BRIEF_CSS}</head><body>{body}</body></html>"


def _article_html(title: str, html_body: str) -> str:
    h1 = f'<h1>{title}</h1>' if title else ''
    return f"<!DOCTYPE html><html><head>{_ARTICLE_CSS}</head><body>{h1}{html_body}</body></html>"
