"""WebVTT for a span of a recording, so that a file cut out of it carries its own captions.

The transcript of the whole recording is timed against the whole recording, and a part cut out of it
starts at zero, so the cues have to be selected, shifted and clipped. A cue that straddles the cut is
kept and clipped rather than dropped, since the alternative is a file whose first sentence is missing.

A transcriber returns a segment, which is not a subtitle: on one defence 41% of them ran past two
lines and 19% past seven seconds, the longest 335 characters over 25 s. So a cue is broken until it
fits, at a sentence end where there is one and at a word otherwise, and its time is shared out by
the length of the pieces. Word timings would place the breaks properly, and the transcriber is not
asked for them, so the division is proportional and can sit a little early or late inside a long
sentence.

Lines are wrapped at 42 characters over at most two lines, which is what the subtitling guides ask
for and what a player can show without covering the slide. Where a diarization exists, a cue carries
its speaker as a WebVTT voice span, but only where the speaker changes, which is how a subtitler
marks a turn and which keeps the name off the 400 cues in between. ``speakers="always"`` puts it on
every cue, for an archive that indexes them; ``"never"`` leaves it out, for a player that shows an
unrecognised voice span as literal text.
"""
from __future__ import annotations
import json
from pathlib import Path

WIDTH = 42
MAX_LINES = 2
MAX_CHARS = WIDTH * MAX_LINES
MAX_CUE_S = 7.0
MIN_CUE_S = 0.5


def timestamp(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"


def wrap(text: str, width: int = WIDTH, max_lines: int = MAX_LINES) -> str:
    """Break a cue over at most ``max_lines`` lines of about ``width`` characters.

    A cue longer than that is left on the last line rather than truncated: losing words is worse
    than a long line, and the transcript is the record of what was said.
    """
    words, lines, line = (text or "").split(), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width and len(lines) < max_lines - 1:
            lines.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        lines.append(line)
    return "\n".join(lines)


def _pieces(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Pack words into pieces of at most ``max_chars``, ending one at a full stop where that lands
    past half the budget, since a subtitle that ends with the sentence reads better."""
    pieces, cur = [], ""
    for w in (text or "").split():
        cand = f"{cur} {w}".strip()
        if cur and len(cand) > max_chars:
            pieces.append(cur); cur = w
        else:
            cur = cand
        if cur.endswith((".", "?", "!", "…")) and len(cur) >= max_chars * 0.5:
            pieces.append(cur); cur = ""
    if cur:
        pieces.append(cur)
    return pieces or [""]


def split_cue(cue: dict, max_chars: int = MAX_CHARS, max_s: float = MAX_CUE_S) -> list[dict]:
    """One transcriber segment as the subtitles it should have been."""
    text = (cue.get("text") or "").strip()
    start, end = float(cue["start"]), float(cue["end"])
    span = max(0.0, end - start)
    pieces = _pieces(text, max_chars)
    # A piece can still be too slow to leave on screen, so divide it again by its own duration.
    total = sum(len(p) for p in pieces) or 1
    out, t = [], start
    for p in pieces:
        share = span * len(p) / total
        n = max(1, int(-(-share // max_s)))
        if n == 1:
            sub = [p]
        else:
            words = p.split()
            per = max(1, -(-len(words) // n))
            sub = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
        each = share / len(sub)
        for q in sub:
            # A cue no longer than max_s even where it cannot be divided further, since a caption
            # should not sit over the pause that follows the words.
            out.append({"start": t, "end": min(t + each, t + max_s), "text": q,
                        "speaker": cue.get("speaker")})
            t += each
    return out or [dict(cue)]


def deoverlap(cues: list[dict], floor: float = 0.2) -> list[dict]:
    """No two cues on screen at once.

    The transcriber's segments do overlap, by a second or so wherever one speaker comes in over
    another, and a player draws both. The earlier cue is ended where the next begins rather than the
    later one delayed, so every cue stays on the words it belongs to.
    """
    out = sorted(cues, key=lambda c: (c["start"], c["end"]))
    for a, b in zip(out, out[1:]):
        if a["end"] <= b["start"]:
            continue
        if b["start"] - a["start"] >= floor:
            a["end"] = b["start"]
        else:
            b["start"] = a["end"] = a["start"] + floor
            b["end"] = max(b["end"], b["start"] + floor)
    return out


def speaker_at(turns: list[dict], start: float, end: float) -> str | None:
    """Whose turn covers most of this cue."""
    best, who = 0.0, None
    for t in turns or []:
        overlap = min(end, float(t["end"])) - max(start, float(t["start"]))
        if overlap > best:
            best, who = overlap, t.get("speaker")
    return who


def load_transcript(analysis_dir: Path) -> list[dict]:
    """The cues of the whole recording, from the whole-file pass or the per-segment one."""
    full = analysis_dir / "whisper_full.json"
    if full.exists():
        return [s for s in json.loads(full.read_text())["segments"] if (s.get("text") or "").strip()]
    per = analysis_dir / "transcripts.json"
    if per.exists():
        return sorted(([p for v in json.loads(per.read_text()).values() for p in (v.get("parts") or [])
                        if (p.get("text") or "").strip()]), key=lambda p: p["start"])
    raise FileNotFoundError(f"no transcript in {analysis_dir}")


def cues_for_span(cues: list[dict], start: float, end: float, turns: list[dict] | None = None,
                  names: dict | None = None) -> list[dict]:
    """The cues of one span, shifted to start at zero and clipped to its ends."""
    out = []
    for c in cues:
        a, b = float(c["start"]), float(c["end"])
        if b <= start or a >= end:
            continue
        who = speaker_at(turns, a, b) if turns else None
        out.extend(split_cue({"start": max(a, start) - start, "end": min(b, end) - start,
                              "text": (c.get("text") or "").strip(),
                              "speaker": (names or {}).get(who, who) if who else None}))
    return deoverlap(out)


def write_vtt(cues: list[dict], out: Path, speakers: str | bool = "change") -> Path:
    """``speakers``: ``"change"`` names a voice where it takes over, ``"always"`` on every cue,
    ``"never"`` not at all. ``True`` and ``False`` are read as ``"always"`` and ``"never"``."""
    mode = {True: "always", False: "never"}.get(speakers, speakers)
    lines, previous = ["WEBVTT", ""], None
    for k, c in enumerate(cues, 1):
        text = wrap(c["text"])
        who = c.get("speaker")
        if who and (mode == "always" or (mode == "change" and who != previous)):
            text = f"<v {who}>{text}"
        previous = who or previous
        # A cue too short to read is stretched to the floor, but never over the cue after it: two
        # captions on screen at once is the worse fault, and the floor is what used to cause it.
        end = max(float(c["end"]), float(c["start"]) + MIN_CUE_S)
        if k < len(cues):
            end = min(end, max(float(c["end"]), float(cues[k]["start"])))
        lines += [str(k), f"{timestamp(c['start'])} --> {timestamp(end)}", text, ""]
    out.write_text("\n".join(lines))
    return out


def cues_for_spans(cues: list[dict], spans: list[tuple[float, float]], turns: list[dict] | None = None,
                   names: dict | None = None) -> list[dict]:
    """The cues of a file joined from several spans of the recording, end to end: each span's cues
    start where the previous span's picture ends, so a stop taken out of the middle of a part leaves
    the captions in step with the cut."""
    out, offset = [], 0.0
    for start, end in spans:
        for c in cues_for_span(cues, float(start), float(end), turns, names):
            out.append(c | {"start": c["start"] + offset, "end": c["end"] + offset})
        offset += float(end) - float(start)
    return out


def _spans_of(s: dict) -> list[tuple[float, float]]:
    """``{"spans": [[a, b], ...]}`` or the single ``{"start_s", "end_s"}``."""
    if s.get("spans"):
        return [(float(a), float(b)) for a, b in s["spans"]]
    return [(float(s["start_s"]), float(s["end_s"]))]


def for_spans(analysis_dir: Path, spans: dict, out_dir: Path, speakers: str | bool = "change", log=print) -> dict:
    """One ``.vtt`` per span. ``spans`` maps an output stem to ``{"start_s", "end_s"}``, or to
    ``{"spans": [[start, end], ...]}`` for a file joined from several spans of the recording.

    Returns the number of cues written for each, so that a span with none is visible rather than a
    silently empty file.
    """
    cues = load_transcript(analysis_dir)
    turns, names = None, {}
    seg = analysis_dir / "segments.json"
    if speakers not in (False, "never") and seg.exists():
        d = json.loads(seg.read_text())
        sp = d.get("speakers") or {}
        turns = sp.get("turns")
        names = {k: (v.get("name") or k) for k, v in (sp.get("speakers") or {}).items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for stem, s in spans.items():
        sp = _spans_of(s)
        part = cues_for_spans(cues, sp, turns, names)
        out = out_dir / f"{Path(stem).stem}.vtt"
        write_vtt(part, out, speakers)
        written[out.name] = len(part)
        log(f"  {out.name}: {len(part)} cues over {sum(b - a for a, b in sp):.0f} s in {len(sp)} span(s)")
    return written
