"""Export the trip plan as a standalone, printable HTML page.

The agents write markdown. This turns it into one self-contained .html file that
opens in any browser (double-click it) and prints cleanly, so Print -> Save as PDF
gives you a PDF without any PDF library.
"""
from __future__ import annotations

import html
import re

import markdown

CSS = """
:root { --ink:#1f2328; --muted:#59636e; --line:#d8dee4; --accent:#d6336c; --bg:#ffffff; --soft:#f6f8fa; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 820px; margin: 0 auto; padding: 40px 24px 64px; }
h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 .25rem; color: var(--accent); }
h2 { font-size: 1.35rem; margin: 2.25rem 0 .75rem; padding-bottom: .35rem; border-bottom: 2px solid var(--line); }
h3 { font-size: 1.1rem; margin: 1.5rem 0 .5rem; }
p, li { margin: .3rem 0; }
hr { display: none; }
table { border-collapse: collapse; width: 100%; margin: .75rem 0; font-size: .95rem; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: var(--soft); }
code { background: var(--soft); padding: 1px 5px; border-radius: 4px; font-size: .9em; }
blockquote { margin: .75rem 0; padding: .25rem 1rem; border-left: 4px solid var(--accent); color: var(--muted); }
.box { list-style: none; padding-left: 0; }
.footer { margin-top: 3rem; color: var(--muted); font-size: .85rem; }
@media print {
  main { padding: 0; max-width: none; }
  h2 { break-after: avoid; }
  h3, table, li { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
"""


def plan_to_html(plan_markdown: str, title: str = "Trip plan") -> str:
    # markdown has no checkbox syntax, so turn "- [ ] item" into a printable box first
    md = re.sub(r"^(\s*)- \[ \] ", r"\1- ☐ ", plan_markdown, flags=re.M)
    md = re.sub(r"^(\s*)- \[x\] ", r"\1- ☑ ", md, flags=re.M | re.I)
    # this renderer needs a blank line before a list or table; agents often skip it
    md = re.sub(r"^(?!\s*(?:[-*] |\d+\. |\|))(\S.*)\n(?=\s*(?:[-*] |\d+\. |\|))", r"\1\n\n", md, flags=re.M)
    body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head><body><main>
{body}
<p class="footer">Planned by TripMate · a multi-agent trip planner built with Claude + MCP. To save as PDF: File → Print → Save as PDF.</p>
</main></body></html>"""
