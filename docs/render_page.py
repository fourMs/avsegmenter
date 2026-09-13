"""Render a docs/*.md page as a standalone HTML page in the UiO/DAM look (used for the HUMIT page)."""
from __future__ import annotations
import html
import re
import sys
from pathlib import Path

HEAD = '''<title>{title}</title>
<style>
:root{{--paper:#f8fafc;--card:#fff;--ink:#0f172a;--ink2:#475569;--line:#e2e8f0;--accent:#4c6239}}
:root[data-theme="dark"]{{--paper:#0f172a;--card:#1e293b;--ink:#e2e8f0;--ink2:#94a3b8;--line:#334155;--accent:#8fae76}}
body{{background:var(--paper);color:var(--ink);font:17px/1.55 Helvetica,Arial,sans-serif;padding-block:36px 60px;padding-inline:20px}}
.wrap{{max-width:820px;margin:0 auto}}
h1{{font:400 40px/1.2 Helvetica,Arial,sans-serif;margin:0 0 6px;text-wrap:balance}}
h2{{font:400 31px/1.25 Helvetica,Arial,sans-serif;margin:36px 0 10px;text-wrap:balance}}
p{{max-width:70ch;margin:0 0 12px}} p:first-of-type{{color:var(--ink2)}}
a{{color:var(--ink);text-decoration:underline;text-underline-offset:.2em;text-decoration-thickness:.05em}}
code{{font-family:Menlo,Consolas,"Liberation Mono",monospace;font-size:14px;background:var(--card);border:1px solid var(--line);padding:1px 5px;border-radius:3px}}
table{{width:100%;border-collapse:collapse;font-size:15px;margin:8px 0 14px;display:block;overflow-x:auto}}
th{{text-align:left;color:var(--ink2);font-weight:400;padding:8px 10px 8px 0;border-bottom:1px solid var(--line)}} td{{padding:8px 10px 8px 0;border-bottom:1px solid var(--line);vertical-align:top}}
ul,ol{{padding-left:22px;max-width:72ch}} li{{margin:4px 0}}
</style>
'''


def inline(t: str) -> str:
    t = html.escape(t); t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t); return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", t)


def render(md: str, title: str) -> str:
    out = []; lines = md.splitlines(); i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("# "): out.append(f"<h1>{inline(l[2:])}</h1>")
        elif l.startswith("## "): out.append(f"<h2>{inline(l[3:])}</h2>")
        elif l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells): rows.append(cells)
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]) + "</tbody></table>"); continue
        elif re.match(r"^\d+\. ", l):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]): items.append(re.sub(r"^\d+\. ", "", lines[i])); i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>"); continue
        elif l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "): items.append(lines[i][2:]); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"); continue
        elif l.strip().startswith("```"):
            code = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"): code.append(lines[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
        elif l.strip():
            para = [l]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||- |\d+\. |```)", lines[i + 1]): i += 1; para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return HEAD.format(title=html.escape(title)) + '<div class="wrap">' + "\n".join(out) + "</div>\n"


if __name__ == "__main__":
    src, dst, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    dst.write_text(render(src.read_text(), title)); print(dst)
