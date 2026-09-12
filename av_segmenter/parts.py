"""Parts of a talk-heavy recording: trial lecture, introduction, opponents, breaks.

Boundaries come from three cues: a long non-speech gap (a break), an applause burst (the end of
something), and a change in who dominates the floor (one opponent hands over to the next). Parts
shorter than a few minutes are merged into their neighbours; optional plan titles are attached by
running order.
"""
from __future__ import annotations
import numpy as np
from .fusion import Segment


def dominant_speaker_track(turns: list[dict], duration: float, window_s: float = 300.0, hop_s: float = 30.0) -> tuple[np.ndarray, list[str | None]]:
    """Who holds the floor in each sliding window (None where nobody speaks)."""
    t = np.arange(0, max(0.0, duration - window_s) + hop_s, hop_s)
    dom: list[str | None] = []
    for a in t:
        b = a + window_s
        share: dict[str, float] = {}
        for tr in turns:
            ov = min(b, tr["end"]) - max(a, tr["start"])
            if ov > 0:
                share[tr["speaker"]] = share.get(tr["speaker"], 0.0) + ov
        dom.append(max(share, key=share.get) if share and max(share.values()) > 0.2 * window_s else None)
    return t + window_s / 2, dom


def find_parts(segs: list[Segment], turns: list[dict], duration: float, gap_s: float = 90.0, min_s: float = 240.0,
               applause_min_s: float = 5.0, speaker_min_total_s: float = 300.0, dedupe_s: float = 180.0) -> list[dict]:
    """Parts from three cues: a silence at least ``gap_s`` long (a break; the part resumes when speech returns),
    an applause burst (the end of something), and the first sustained turn of a speaker who goes on to speak
    for at least ``speaker_min_total_s`` (an opponent taking the floor). Cues within ``dedupe_s`` of each other
    collapse into one; parts shorter than ``min_s`` merge into their neighbours; a span that is mostly
    non-speech is a break rather than a part."""
    cuts: list[tuple[float, str]] = []
    for s in segs:                                                        # breaks: silence only (demos are 'other'/'music')
        if s.kind == "silence" and s.duration >= gap_s:
            cuts.append((s.start, "break")); cuts.append((s.end, "break-end"))
    for s in segs:                                                        # applause ends a part
        if s.kind == "applause" and s.duration >= applause_min_s:
            cuts.append((s.end, "applause"))
    if turns:                                                             # a major voice arrives
        total: dict[str, float] = {}
        for t in turns:
            total[t["speaker"]] = total.get(t["speaker"], 0.0) + t["end"] - t["start"]
        for spk, tot in total.items():
            if tot < speaker_min_total_s:
                continue
            first = next((t["start"] for t in turns if t["speaker"] == spk and t["end"] - t["start"] >= 20), None)
            if first is not None and first > 60:
                cuts.append((float(first), f"speaker:{spk}"))
    cuts.sort()
    merged: list[tuple[float, list[str]]] = []
    for c, w in cuts:
        if merged and c - merged[-1][0] <= dedupe_s and not (w.startswith("break") or merged[-1][1][-1].startswith("break")):
            merged[-1] = (merged[-1][0] if w.startswith("speaker") else c, merged[-1][1] + [w])   # keep the applause time
        else:
            merged.append((c, [w]))
    edges = [0.0] + [c for c, _ in merged] + [duration]
    whys = [["start"]] + [w for _, w in merged]
    parts = [{"start": a, "end": b, "cues": whys[i]} for i, (a, b) in enumerate(zip(edges, edges[1:])) if b - a > 0]

    def speech_share(a: float, b: float) -> float:
        sp = sum(min(b, s.end) - max(a, s.start) for s in segs if s.kind == "speech" and s.end > a and s.start < b)
        return sp / max(1e-9, b - a)

    # merging: a short span of talk joins the neighbouring talk (previous unless that is a break); a short quiet
    # span joins the previous span; a long quiet span stays as a break
    changed = True
    while changed and len(parts) > 1:
        changed = False
        for k, pt in enumerate(parts):
            d = pt["end"] - pt["start"]; talk = speech_share(pt["start"], pt["end"]) >= 0.35
            if (talk and d >= min_s) or (not talk and d >= 60.0):
                continue
            prev = parts[k - 1] if k > 0 else None
            nxt = parts[k + 1] if k + 1 < len(parts) else None
            prev_talk = prev is not None and speech_share(prev["start"], prev["end"]) >= 0.35
            if talk and prev is not None and not prev_talk and nxt is not None:
                nxt["start"] = pt["start"]; nxt["cues"] = pt["cues"] + nxt["cues"]
            elif prev is not None:
                prev["end"] = pt["end"]; prev["cues"] += pt["cues"]
            elif nxt is not None:
                nxt["start"] = pt["start"]; nxt["cues"] = pt["cues"] + nxt["cues"]
            else:
                continue
            del parts[k]; changed = True
            break
    for pt in parts:
        pt["speech_share"] = round(speech_share(pt["start"], pt["end"]), 3)
        pt["kind"] = "part" if pt["speech_share"] >= 0.35 else "break"
        pt["cues"] = sorted(set(pt["cues"]), key=pt["cues"].index)
    n = 0
    for pt in parts:
        if pt["kind"] == "part":
            n += 1; pt["index"] = n
        pt["start"] = round(pt["start"], 2); pt["end"] = round(pt["end"], 2); pt["duration"] = round(pt["end"] - pt["start"], 2)
    return parts


def title_parts(parts: list[dict], acts: list[dict], roles: dict | None = None) -> None:
    """Attach plan acts to the parts by running order. A short part that is almost all the chair's voice
    (an opening, a hand-over) does not consume an act; with more parts than acts, the acts go to the longest
    parts (in chronological order) and the rest keep generic titles; with fewer, trailing acts are unused."""
    real = [p for p in parts if p["kind"] == "part"]
    chair = {s for s, r in (roles or {}).items() if r and r.startswith("chair")}
    for pt in parts:
        pt["title"] = "Break" if pt["kind"] == "break" else f"Part {pt['index']}"
        pt["plan"] = None
        top = next(iter(pt.get("speakers") or {}), None)
        if pt["kind"] == "part" and top in chair and (pt.get("speakers") or {}).get(top, 0) >= 0.8 and pt["duration"] < 600:
            pt["title"] = "Chair"
    real = [p for p in real if p["title"] != "Chair"]
    if not acts or not real:
        return
    chosen = sorted(sorted(real, key=lambda p: -p["duration"])[:len(acts)], key=lambda p: p["start"])
    for pt, a in zip(chosen, acts):
        pt["plan"] = a
        pt["title"] = a.get("act") or a.get("work") or pt["title"]
