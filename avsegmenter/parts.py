"""Parts of a recording: trial lecture, introduction, opponents, contributions, breaks.

Boundaries come from three cues: a long non-speech gap (a break), an applause burst (the end of
something), and a change in who dominates the floor (one opponent hands over to the next). Parts
shorter than a few minutes are merged into their neighbours; optional plan titles are attached by
running order.

Applause alone does not end a part. At a concert the audience applauds between pieces, and the
pieces, not the parts, carry that structure: a concert has two parts and an interval. So applause
cuts only where talk follows it, which is the hand-over at a defence or a seminar.

That rule loses a mixed event, where a contribution is applauded and a performance follows rather
than a speech. Instead of loosening it for every recording, the detector uses the running order:
where ``expect_parts`` says how many acts there were and the pass above has found fewer, the longest
parts are split again at the applause inside them, strongest burst first, until the count is reached
or there is no applause left to cut on. A recording with no running order behaves exactly as before.
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
               applause_min_s: float = 5.0, speaker_min_total_s: float = 300.0, dedupe_s: float = 180.0,
               expect_parts: int | None = None, split_floor_s: float = 120.0,
               slide_cues: list[dict] | None = None) -> list[dict]:
    """Parts from three cues: a silence at least ``gap_s`` long (a break; the part resumes when speech returns),
    an applause burst (the end of something), and the first sustained turn of a speaker who goes on to speak
    for at least ``speaker_min_total_s`` (an opponent taking the floor). Cues within ``dedupe_s`` of each other
    collapse into one; parts shorter than ``min_s`` merge into their neighbours; a span that is mostly
    non-speech is a break rather than a part.

    ``expect_parts`` is the number of acts in the running order, where one is known. When the pass above
    finds fewer parts than that, the longest parts are split again at the applause inside them, strongest
    first, leaving at least ``split_floor_s`` on each side.

    ``slide_cues`` are the title cards read off the projection (``slides.title_cues``). A hall that
    projects the name of each act marks its boundaries better than any sound does: the slide changes
    when the act changes, whether or not the room applauds and whether or not the host says anything.
    While a card is up the act is running, so a change of voice inside its span does not cut."""
    cuts: list[tuple[float, str]] = []
    for s in segs:                                                        # breaks: silence only (demos are 'other'/'music')
        if s.kind == "silence" and s.duration >= gap_s:
            cuts.append((s.start, "break")); cuts.append((s.end, "break-end"))
    def talk_share(a: float, b: float) -> float:
        sp = sum(min(b, x.end) - max(a, x.start) for x in segs if x.kind == "speech" and x.end > a and x.start < b)
        return sp / max(1e-9, b - a)

    def content_share(a: float, b: float) -> float:
        """Music, talk or applause, as opposed to silence and room noise."""
        sp = sum(min(b, x.end) - max(a, x.start) for x in segs if x.kind in ("music", "speech", "applause") and x.end > a and x.start < b)
        return sp / max(1e-9, b - a)

    applause_cues: list[tuple[float, float]] = []                         # (time, how long the applause lasted)
    for s in segs:
        if s.kind != "applause" or s.duration < applause_min_s:
            continue
        if content_share(s.end, min(duration, s.end + 300)) >= 0.5:       # something follows: a candidate boundary
            applause_cues.append((s.end, s.duration))
        if talk_share(s.end, min(duration, s.end + 300)) >= 0.7:          # talk follows: a boundary on its own
            cuts.append((s.end, "applause"))                              # (in a concert applause is followed by the next piece)
    if turns:                                                             # a major voice arrives
        total: dict[str, float] = {}
        for t in turns:
            total[t["speaker"]] = total.get(t["speaker"], 0.0) + t["end"] - t["start"]
        def share_after(spk: str, t0: float, win: float = 300.0) -> float:
            tot_s = sum(min(t0 + win, t["end"]) - max(t0, t["start"]) for t in turns if t["speaker"] == spk and t["end"] > t0 and t["start"] < t0 + win)
            return tot_s / win
        for spk, tot in total.items():
            if tot < speaker_min_total_s:
                continue
            # arrival: the first turn from which this voice holds at least half of the next five minutes
            first = next((t["start"] for t in turns if t["speaker"] == spk and t["end"] - t["start"] >= 10 and share_after(spk, t["start"]) >= 0.5), None)
            if first is not None and first > 60:
                cuts.append((float(first), f"speaker:{spk}"))
    if slide_cues:
        # A card that is still up says the act is still running, whatever the voices do: a panellist
        # who holds the floor for ten minutes is not a new part. So a voice cue inside a card's own
        # span is dropped, while applause and breaks, which are events in the room, are kept.
        spans = [(float(c["t"]), float(c.get("end", c["t"]))) for c in slide_cues]
        cuts = [(t, w) for (t, w) in cuts
                if not (w.startswith("speaker") and any(a < t < b for a, b in spans))]
    for cue in (slide_cues or []):                                        # a new title card: an act begins
        cuts.append((float(cue["t"]), "slide"))
    cuts.sort()
    merged: list[tuple[float, list[str]]] = []
    for c, w in cuts:
        near = merged and c - merged[-1][0] <= dedupe_s
        # two title cards are two acts, however close together, and a break is always its own edge
        both_slides = w == "slide" and merged and "slide" in merged[-1][1]
        keeps_apart = both_slides or w.startswith("break") or (merged and merged[-1][1][-1].startswith("break"))
        if near and not keeps_apart:
            # a title card is the surest boundary: it takes the time, and the softer cue joins it
            time = c if (w == "slide" or w.startswith("speaker")) else merged[-1][0]
            if w != "slide" and "slide" in merged[-1][1]:
                time = merged[-1][0]
            merged[-1] = (time, merged[-1][1] + [w])
        else:
            merged.append((c, [w]))
    edges = [0.0] + [c for c, _ in merged] + [duration]
    whys = [["start"]] + [w for _, w in merged]
    parts = [{"start": a, "end": b, "cues": whys[i]} for i, (a, b) in enumerate(zip(edges, edges[1:])) if b - a > 0]

    speech_share = content_share

    # merging: a short span of content joins the neighbouring content (previous unless that is a break); a short
    # quiet span joins the previous span; a long quiet span stays as a break
    changed = True
    while changed and len(parts) > 1:
        changed = False
        for k, pt in enumerate(parts):
            d = pt["end"] - pt["start"]; talk = speech_share(pt["start"], pt["end"]) >= 0.35
            if (talk and d >= min_s) or (not talk and d >= 60.0):
                continue
            if "slide" in pt["cues"] and d >= split_floor_s:
                continue          # a title card says this is an act of its own, however short
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
    # Where the running order says how many acts there were, and the merging above has left fewer
    # parts than that, split the longest parts again at the applause inside them. Strongest applause
    # first: a longer burst is a surer boundary than a short one, and a part is only cut where both
    # sides keep at least split_floor_s.
    if expect_parts:
        used = {round(p["start"], 2) for p in parts}
        while len([p for p in parts if content_share(p["start"], p["end"]) >= 0.35]) < expect_parts:
            best = None
            for t, strength in sorted(applause_cues, key=lambda c: -c[1]):
                if round(t, 2) in used:
                    continue
                host = next((p for p in parts if p["start"] + split_floor_s <= t <= p["end"] - split_floor_s), None)
                if host is None:
                    continue
                if best is None or (host["end"] - host["start"]) > (best[1]["end"] - best[1]["start"]):
                    best = (t, host, strength)
            if best is None:
                break
            t, host, _ = best
            parts.insert(parts.index(host) + 1, {"start": t, "end": host["end"], "cues": ["applause:split"]})
            host["end"] = t
            used.add(round(t, 2))
            parts.sort(key=lambda p: p["start"])

    for pt in parts:
        pt["content_share"] = round(content_share(pt["start"], pt["end"]), 3)
        pt["speech_share"] = round(talk_share(pt["start"], pt["end"]), 3)
        pt["kind"] = "part" if pt["content_share"] >= 0.35 else "break"
        pt["cues"] = sorted(set(pt["cues"]), key=pt["cues"].index)
    n = 0
    for pt in parts:
        if pt["kind"] == "part":
            n += 1; pt["index"] = n
        pt["start"] = round(pt["start"], 2); pt["end"] = round(pt["end"], 2); pt["duration"] = round(pt["end"] - pt["start"], 2)
    return parts


def title_parts(parts: list[dict], acts: list[dict], roles: dict | None = None,
                assignments: dict[str, int | None] | None = None) -> None:
    """Attach plan acts to the parts.

    With ``assignments``, a part id maps to the index of the act announced in it, worked out from what
    was said rather than from the printed order. That matters whenever an event runs in a different
    order from its announcement, which is common: a panel is moved, a performance closes the evening.

    Without it, the acts go by running order. A short part that is almost all the chair's voice (an
    opening, a hand-over) does not consume an act; with more parts than acts, the acts go to the longest
    parts, in chronological order, and the rest keep generic titles; with fewer, trailing acts are unused."""
    real = [p for p in parts if p["kind"] == "part"]
    chair = {s for s, r in (roles or {}).items() if r and ("chair" in r or "host" in r)}
    for pt in parts:
        pt["title"] = "Break" if pt["kind"] == "break" else f"Part {pt['index']}"
        pt["plan"] = None
        top = next(iter(pt.get("speakers") or {}), None)
        if pt["kind"] == "part" and top in chair and (pt.get("speakers") or {}).get(top, 0) >= 0.8 and pt["duration"] < 600:
            pt["title"] = "Chair"
    real = [p for p in real if p["title"] != "Chair"]
    if not acts or not real:
        return
    if assignments:
        for pt in parts:
            j = assignments.get(pt.get("id"))
            if j is None or not (0 <= j < len(acts)):
                continue
            pt["plan"] = acts[j]
            pt["title"] = acts[j].get("act") or acts[j].get("work") or pt["title"]
        return
    chosen = sorted(sorted(real, key=lambda p: -p["duration"])[:len(acts)], key=lambda p: p["start"])
    for pt, a in zip(chosen, acts):
        pt["plan"] = a
        pt["title"] = a.get("act") or a.get("work") or pt["title"]
