"""A shareable HTML report from segments.json: timeline, plan vs. performed, pieces, and what the numbers mean."""
from __future__ import annotations
import base64
import html
import json
from pathlib import Path

COL = {"music": "var(--music)", "speech": "var(--talk)", "applause": "var(--applause)", "silence": "var(--silence)", "other": "var(--other)"}
NAMES = [("music", "Music"), ("speech", "Talk"), ("applause", "Applause"), ("silence", "Silence"), ("other", "Other")]
DASH = "–"
CSS = """
/* UiO web profile (Helvetica/Arial, black text, normal-weight headings, underlined links) on the DAM palette (slate ground, white cards, swamp-green accent) */
:root{--paper:#f8fafc;--card:#ffffff;--ink:#0f172a;--ink2:#475569;--line:#e2e8f0;--accent:#4c6239;--music:#2f5bd6;--talk:#d08a1a;--applause:#1f9a6a;--silence:#8d929c;--other:#8a5bc4;--flag:#b60000;--flagbg:#fdecec}
:root[data-theme="dark"]{--paper:#0f172a;--card:#1e293b;--ink:#e2e8f0;--ink2:#94a3b8;--line:#334155;--accent:#8fae76;--music:#5b82ec;--talk:#e3a444;--applause:#38b483;--silence:#6f7683;--other:#a57de0;--flag:#ff8080;--flagbg:#3a1c1c}
body{background:var(--paper);color:var(--ink);font:17px/1.5 Helvetica,Arial,sans-serif;padding-block:32px 56px;padding-inline:20px}
.wrap{max-width:900px;margin:0 auto;display:grid;gap:40px}
h1,h2,h3{font-family:Helvetica,Arial,sans-serif;font-weight:400;text-wrap:balance;margin:0}
h1{font-size:40px;line-height:1.2} h2{font-size:31px;margin-bottom:12px} h3{font-size:21px;margin-top:2px}
a{color:var(--ink);text-decoration:underline;text-underline-offset:.2em;text-decoration-thickness:.05em}
.eyebrow{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);margin-bottom:8px}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--ink2);margin-top:10px;font-size:15px} .facts b{color:var(--ink);font-weight:400}
.tc,.dur,.tk,.num{font-family:Menlo,Consolas,"Liberation Mono",monospace;font-variant-numeric:tabular-nums}
svg{width:100%;height:auto;display:block} .num{font-size:15px;fill:var(--ink);font-weight:700;font-family:Helvetica,Arial,sans-serif} .tk{font-size:12px;fill:var(--ink2)} .tick{stroke:var(--line);stroke-width:1.5}
.legend{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:14px;color:var(--ink2);margin-top:8px} .legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px} .legend b{color:var(--ink);font-weight:400;margin-left:4px}
table{width:100%;border-collapse:collapse;font-size:15px} td{padding:9px 10px 9px 0;border-top:1px solid var(--line);vertical-align:top} tr:first-child td{border-top:0} td.tc{width:2.2em;color:var(--ink2)}
.ok{color:var(--accent)} .no{color:var(--flag)}
.pieces{display:grid;gap:14px}
.piece{display:grid;grid-template-columns:34px 200px 1fr;gap:16px;background:var(--card);border:1px solid var(--line);padding:16px;border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.pn{font-size:30px;line-height:1;color:var(--accent)}
.piece figure{margin:0} .piece img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:6px;display:block;background:#000}
.pb header{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px} .tc{font-size:14px} .dur{font-size:13px;color:var(--ink2)}
.who{margin:0 0 8px;color:var(--ink2)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;margin:0;font-size:15px} dt{color:var(--ink2)} dd{margin:0}
.dim{color:var(--ink2)} .flag{font-size:12px;padding:1px 6px;border-radius:3px;background:var(--flagbg);color:var(--flag);vertical-align:1px}
.qa{display:grid;gap:14px} .qa div{display:grid;grid-template-columns:170px 1fr;gap:14px;padding-top:12px;border-top:1px solid var(--line)} .qa div:first-child{border-top:0;padding-top:0} .qa b{font-weight:400} .qa p{margin:0;max-width:66ch}
.verdict{font-size:12px;letter-spacing:.06em;text-transform:uppercase;display:block;margin-top:4px} .yes{color:var(--accent)} .part{color:var(--talk)} .nov{color:var(--flag)}
code{font-family:Menlo,Consolas,"Liberation Mono",monospace;font-size:14px;background:var(--card);border:1px solid var(--line);padding:1px 5px;border-radius:3px}
footer{color:var(--ink2);font-size:14px;border-top:1px solid var(--line);padding-top:14px}
@media (max-width:640px){.piece{grid-template-columns:28px 1fr} .piece figure{grid-column:2} .pb{grid-column:1/-1} .qa div{grid-template-columns:1fr} h1{font-size:32px}}
"""


def _f(t):
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"


def _h(x):
    return html.escape(str(x))


def _clean(v):
    return v if v and v not in ("–", "-") else None


def _work(a):
    work = a.get("work", "") or ""
    work = work.split(":", 1)[1] if ":" in work else work
    return " / ".join(w.strip(" ,/") for w in work.split("/") if w.strip(" ,/"))


def build_report(analysis_dir, title=None, eyebrow="", qa=None, notes=None) -> str:
    """HTML for one analysis folder. `qa` is a list of (question, verdict, css class, answer html);
    `notes` maps a plan act number to a remark shown in the plan table."""
    A = Path(analysis_dir)
    d = json.loads((A / "segments.json").read_text())
    dur = d["video"]["duration"]
    W, H = 1000, 46
    rects = "".join(
        f'<rect x="{s["start"] / dur * W:.2f}" y="6" width="{max(1.2, (s["end"] - s["start"]) / dur * W):.2f}" height="{H}" '
        f'fill="{COL[s["kind"]]}"><title>{_f(s["start"])}{DASH}{_f(s["end"])} {_h(s.get("title") or s["kind"])}</title></rect>'
        for s in d["segments"])
    labels = "".join(f'<text x="{(p["start"] + p["end"]) / 2 / dur * W:.1f}" y="{H + 24}" text-anchor="middle" class="num">{p["index"]}</text>' for p in d["pieces"])
    ticks = "".join(
        f'<line x1="{t / dur * W:.1f}" y1="{H + 30}" x2="{t / dur * W:.1f}" y2="{H + 36}" class="tick"/>'
        f'<text x="{t / dur * W:.1f}" y="{H + 50}" text-anchor="middle" class="tk">{t // 60}′</text>'
        for t in range(0, int(dur), 600))
    svg = f'<svg viewBox="0 0 {W} {H + 56}" role="img" aria-label="Timeline coloured by segment type">{rects}{labels}{ticks}</svg>'

    def thumb(p):
        if not p.get("thumbnail") or not (A / p["thumbnail"]).exists():
            return ""
        return f'<img src="data:image/jpeg;base64,{base64.b64encode((A / p["thumbnail"]).read_bytes()).decode()}" alt="">'

    rows = []
    for p in d["pieces"]:
        m = p.get("music") or {}
        perf = p.get("performers") or {}
        pl = p.get("plan") or {}
        cam = p.get("camera") or {}
        inst = ", ".join(i["label"] for i in p["instruments"][:3]) or "no instrument tag"
        gen = ", ".join(i["label"] for i in p["genres"][:2]) or "—"
        tempo = (f'{m["tempo_bpm"]:.0f} bpm' if m.get("tempo_bpm") else "—") + ("" if m.get("tempo_reliable") else ' <span class="flag">weak pulse</span>')
        key = (m.get("key") or "—") + ("" if m.get("key_reliable") else ' <span class="flag">unreliable</span>')
        if perf.get("estimate") is not None:
            pc = f'{perf["estimate"]} <span class="dim">(tightest framing {perf.get("low")}, most in any frame {perf.get("high")})</span>'
        else:
            pc = "—"
        heard = " · ".join(p.get("performer_names_guess") or []) or "no name caught"
        cues = ", ".join(f'{_f(c["t"])} ({c["why"]})' for c in p.get("internal_cues") or []) or "none"
        ttl = _clean(pl.get("work")) or _clean(pl.get("act")) or f"Piece {p['index']}"
        sub = _clean(pl.get("performers")) or pl.get("act", "")
        matched = {"name": "matched by name in the introduction", "order": "placed by running order", "continues": "continues the previous act"}.get(pl.get("match"), "")
        camtxt = (f'{cam.get("shots")} shot(s), {cam.get("framings")} still framing(s), moving {round((cam.get("moving_share") or 0) * 100)}% of the time') if cam else "—"
        plan_span = f'<span class="dur">plan #{_h(pl.get("nr"))} · {_h(matched)}</span>' if pl else ""
        composer = (" · " + _h(pl["composer"])) if _clean(pl.get("composer")) and pl["composer"] != pl.get("performers") else ""
        motion = round(((p.get("motion") or {}).get("qom_mean_norm") or 0) * 100)
        rows.append(
            f'<article class="piece"><div class="pn">{p["index"]}</div><figure>{thumb(p)}</figure><div class="pb">'
            f'<header><span class="tc">{_f(p["start"])}{DASH}{_f(p["end"])}</span><span class="dur">{_f(p["duration"])}</span>{plan_span}</header>'
            f'<h3>{_h(ttl)}</h3><p class="who">{_h(sub)}{composer}</p>'
            f'<dl><dt>Detected as</dt><dd>{_h(p["ensemble"])} · {_h(inst)} · {_h(gen)}</dd><dt>Heard in intro</dt><dd>{_h(heard)}</dd>'
            f'<dt>On stage</dt><dd>{pc}</dd><dt>Camera</dt><dd>{_h(camtxt)}</dd><dt>Singing</dt><dd>{p["singing_p"] * 100:.0f}%</dd>'
            f'<dt>Tempo / key</dt><dd>{tempo} · {key}</dd>'
            f'<dt>Level / motion</dt><dd>{(p.get("level") or {}).get("leq_dbfs", "—")} dBFS Leq · {motion}% of max motion (still camera only)</dd>'
            f'<dt>Song-change cues</dt><dd>{_h(cues)}</dd></dl></div></article>')

    piece_rows = rows
    real_parts = [pt for pt in (d.get("parts") or []) if pt.get("kind") == "part"]
    if len(real_parts) > 1 or not d.get("pieces"):
        rows = []
        spk = (d.get("speakers") or {}).get("speakers") or {}
        name = lambda k: (spk.get(k) or {}).get("name") or k
        role = lambda k: (spk.get(k) or {}).get("role") or ""
        for pt in d["parts"]:
            if pt.get("kind") != "part":
                continue
            share = " · ".join(f"{_h(name(k))} {v:.0%}" for k, v in list((pt.get("speakers") or {}).items())[:4]) or "—"
            perf = (pt.get("performers") or {}).get("estimate")
            cam = pt.get("camera") or {}
            camtxt = (f'{cam.get("shots")} shot(s), moving {round((cam.get("moving_share") or 0) * 100)}% of the time') if cam else "—"
            cues = ", ".join(pt.get("cues") or [])
            rows.append(
                f'<article class="piece"><div class="pn">{pt["index"]}</div><figure></figure><div class="pb">'
                f'<header><span class="tc">{_f(pt["start"])}{DASH}{_f(pt["end"])}</span><span class="dur">{_f(pt["duration"])}</span><span class="dur">boundary from {_h(cues)}</span></header>'
                f'<h3>{_h(pt.get("title") or "Part " + str(pt["index"]))}</h3><p class="who">{_h((pt.get("plan") or {}).get("performers") or "")}</p>'
                f'<dl><dt>Floor</dt><dd>{share}</dd><dt>Speech share</dt><dd>{pt.get("speech_share", 0) * 100:.0f}%</dd>'
                f'<dt>On stage</dt><dd>{perf if perf is not None else "—"}</dd><dt>Camera</dt><dd>{_h(camtxt)}</dd></dl></div></article>')
        speakers_html = "".join(f'<tr><td class="tc">{_h(k)}</td><td>{_h(name(k))}</td><td>{_h(role(k))}</td><td class="tc">{_f(v["total_s"])}</td><td class="tc">{v["turns"]}</td></tr>' for k, v in spk.items())
        speakers_html = f'<section><h2>Speakers</h2><table><tr><td class="dim">id</td><td class="dim">name</td><td class="dim">suggested role</td><td class="dim">speaking</td><td class="dim">turns</td></tr>{speakers_html}</table></section>' if spk else ""
        parts_html = f'<section><h2>Parts as detected</h2><div class="pieces">{"".join(rows)}</div></section>' if rows else ""
        rows = piece_rows
    else:
        spk = (d.get("speakers") or {}).get("speakers") or {}
        name = lambda k: (spk.get(k) or {}).get("name") or k
        role = lambda k: (spk.get(k) or {}).get("role") or ""
        speakers_html = ("<section><h2>Speakers</h2><table><tr><td class=\"dim\">id</td><td class=\"dim\">name</td><td class=\"dim\">suggested role</td><td class=\"dim\">speaking</td><td class=\"dim\">turns</td></tr>"
                         + "".join(f'<tr><td class="tc">{_h(k)}</td><td>{_h(name(k))}</td><td>{_h(role(k))}</td><td class="tc">{_f(v["total_s"])}</td><td class="tc">{v["turns"]}</td></tr>' for k, v in spk.items()) + "</table></section>") if spk else ""
        parts_html = ""

    plan_html = ""
    if d.get("programme"):
        acts = d["programme"]["acts"]
        assign = d["programme"]["assignments"]
        by_act = {}
        for p in d["pieces"]:
            j = assign.get(p["id"])
            if j is not None:
                by_act.setdefault(j, []).append(p)
        prow = []
        for j, a in enumerate(acts):
            ps = by_act.get(j)
            note = (notes or {}).get(str(a.get("nr")), "")
            if ps:
                when = ", ".join(f'{_f(p["start"])}{DASH}{_f(p["end"])}' for p in ps)
                status = f'<span class="ok">performed</span> {when}' + (f' <span class="dim">· {_h(note)}</span>' if note else "")
            else:
                status = '<span class="no">not performed</span>' + (f' · {_h(note)}' if note else "")
            work = _work(a)
            prow.append(f'<tr><td class="tc">{_h(a.get("nr", ""))}</td><td>{_h(a.get("act", ""))}<div class="dim">{_h(work) if _clean(work) else ""}</div></td><td>{status}</td></tr>')
        order = ", ".join(str(acts[assign[p["id"]]].get("nr")) for p in d["pieces"] if assign.get(p["id"]) is not None)
        plan_html = (f'<section><h2>Running order vs. what happened</h2><p class="dim" style="margin:0 0 10px;max-width:66ch">'
                     f'The plan aligned to the detected pieces through the host\'s introductions. Actual order: {_h(order)}.</p>'
                     f'<table>{"".join(prow)}</table></section>')

    summ = d.get("summary") or {}
    legend = "".join(f'<span><i style="background:{COL[k]}"></i>{n} <b>{_f(summ.get(k, 0))}</b></span>' for k, n in NAMES)
    qa_html = "".join(f'<div><b>{_h(q)}<span class="verdict {cls}">{_h(v)}</span></b><p>{a}</p></div>' for q, v, cls, a in (qa or []))
    n_planned = len(d["programme"]["acts"]) if d.get("programme") else None
    n_parts = len([p for p in (d.get("parts") or []) if p.get("kind") == "part"]); n_pieces = len(d.get("pieces") or [])
    facts = (f'<span><b>{_f(dur)}</b> recording</span><span><b>{n_parts}</b> part{"s" if n_parts != 1 else ""} · <b>{n_pieces}</b> piece{"s" if n_pieces != 1 else ""}'
             + (f' of <b>{n_planned}</b> planned acts' if n_planned else "")
             + f'</span><span><b>{len(d["segments"])}</b> segments</span>'
             + f'<span><b>{sum(1 for s in d["segments"] if s["kind"] == "applause")}</b> applause bursts</span>')
    if d.get("camera"):
        facts += f'<span><b>{len(d["camera"]["cuts"])}</b> camera cuts · moving <b>{round(d["camera"]["summary"]["moving"] * 100)}%</b></span>'
    tools = d.get("tools") or {}
    qa_section = f'<section><h2>What the analysis answers</h2><div class="qa">{qa_html}</div></section>' if qa else ""
    return (f'<title>{_h(title or d["title"])}</title>\n'
            
            f'<style>{CSS}</style>\n<div class="wrap">\n'
            f'<section><div class="eyebrow">{_h(eyebrow)}</div><h1>{_h(title or d["title"])}</h1><div class="facts">{facts}</div></section>\n'
            f'<section><div class="eyebrow">Timeline</div>{svg}<div class="legend">{legend}</div></section>\n'
            f'{plan_html}\n{speakers_html}\n{parts_html}\n' + (f'<section><h2>Pieces as detected</h2><div class="pieces">{"".join(rows)}</div></section>\n' if rows else '') + f'{qa_section}\n'
            f'<footer>Generated {_h(d.get("generated", ""))} · musicalgestures {_h(tools.get("musicalgestures"))} · ambiscape {_h(tools.get("ambiscape"))} '
            f'· musiscape {_h(tools.get("musiscape"))} · every field above is an automatic estimate except the plan itself.</footer>\n</div>\n')
