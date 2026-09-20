"""What the room could see: the projected slides, read once every few seconds.

An event that runs from a running order usually projects a title slide when an act begins, with the
act's name and the people in it. That is written rather than spoken, so it survives a bilingual
event, a quiet hand-over and a host who forgets to announce; and it changes exactly when the act
changes, which makes it a boundary cue as well as a name.

Reading it needs optical character recognition, which is an optional dependency: ``pip install
easyocr``. Nothing else in the package requires it, and a recording without slides, or without the
extra package, behaves as before.

    slides = detect_slides(video, out_dir)          # writes out_dir/slides.json, reuses it if there
    cues = title_cues(slides)                       # [{"t", "text"}] where a new slide stays up

The projection area is given as an ffmpeg crop. The default takes the middle of the upper half of
the frame, which is where a hall camera puts a screen; pass ``crop=`` for a different room.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

STEP_S = 10.0
CROP = "crop=iw*0.55:ih*0.45:iw*0.20:ih*0.05,scale=1100:-1"
MIN_CONF = 0.4
MIN_HOLD_S = 20.0
_WORDS = re.compile(r"[^\w\sæøåÆØÅ]", re.UNICODE)


def _key(text: str) -> str:
    """Two readings of the same slide differ in punctuation and the odd letter; compare on the rest."""
    return _WORDS.sub("", (text or "").lower()).strip()[:60]


def _frames(video: Path, step_s: float, crop: str, hwaccel: bool = True):
    """(t, jpeg bytes) once every step_s seconds, decoded on the card where there is one."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if hwaccel:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", str(video), "-vf", f"fps=1/{step_s},{crop}", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    buf, t = b"", 0.0
    while True:
        chunk = proc.stdout.read(1 << 16)
        if not chunk:
            break
        buf += chunk
        while True:
            a = buf.find(b"\xff\xd8")
            b = buf.find(b"\xff\xd9", a + 2)
            if a < 0 or b < 0:
                break
            yield t, buf[a:b + 2]
            buf = buf[b + 2:]
            t += step_s
    proc.wait()


def detect_slides(video: Path, out_dir: Path, step_s: float = STEP_S, crop: str = CROP,
                  languages: tuple[str, ...] = ("no", "en"), gpu: bool = True, log=print) -> list[dict]:
    """Read the projection through the recording. Returns, and caches, one entry per distinct slide."""
    cache = Path(out_dir) / "slides.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        import cv2
        import easyocr
        import numpy as np
    except ImportError as exc:                       # optional: say which package and carry on
        raise ImportError("reading slides needs easyocr and opencv: pip install easyocr") from exc

    reader = easyocr.Reader(list(languages), gpu=gpu, verbose=False)
    slides: list[dict] = []
    for t, jpg in _frames(Path(video), step_s, crop):
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        lines = [txt.strip() for _, txt, conf in reader.readtext(img) if conf > MIN_CONF and len(txt.strip()) > 2]
        text = " / ".join(lines)
        if not text:
            continue
        if slides and _key(text) == _key(slides[-1]["text"]) and t - slides[-1]["end"] <= 2 * step_s:
            slides[-1]["end"] = round(t + step_s, 1)
        else:
            slides.append({"start": round(t, 1), "end": round(t + step_s, 1), "text": text, "lines": lines})
    cache.write_text(json.dumps(slides, ensure_ascii=False, indent=1))
    log(f"slides: {len(slides)} distinct readings")
    return slides


def _titleness(card: dict) -> float:
    """How much a reading looks like a title card rather than a slide from inside a talk.

    A title card names a work and the people in it, so it runs to several words and usually carries a
    comma before an institution, and its first line tends to be set in capitals. A slide from inside a
    talk is a heading, a diagram label or one word."""
    text = card.get("text") or ""
    words = len(text.split())
    first = (card.get("lines") or [text])[0]
    letters = [c for c in first if c.isalpha()]
    caps = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
    return words + 3.0 * text.count(",") + (3.0 if caps > 0.7 else 0.0) + min(4.0, (card["end"] - card["t"]) / 60.0)


def title_cues(slides: list[dict], min_hold_s: float = MIN_HOLD_S, min_words: int = 3,
               strong_words: int = 8, same_ratio: float = 0.8, limit: int | None = None) -> list[dict]:
    """Where a new slide comes up: a boundary, and the text that names what follows.

    Two readings of the same card differ by a comma, the odd letter and sometimes a line the reader
    missed, so consecutive readings that share ``same_ratio`` of their words count as one card, and
    the fullest reading is the one kept. A card counts
    when it holds for ``min_hold_s`` or carries ``strong_words`` words: a title card that is up for
    only a moment, because the hall dims the projection for a performance, still names the act.

    ``limit`` keeps only the most title-like cards, which is what to pass when the running order says
    how many acts there were: a hall shows other slides too, and the acts are the ones announced on a
    card that names people.
    """
    def words(t: str) -> set[str]:
        return {w for w in _key(t).split() if len(w) > 2}

    def same(a: str, b: str, adjacent: bool = False) -> bool:
        """Two readings of one card: the words overlap, whichever of them the reader caught.

        A reading taken moments after another is held to a lower bar, since two different acts ten
        seconds apart is implausible and the reader often loses a line to the light in the hall."""
        wa, wb = words(a), words(b)
        if not wa or not wb:
            return False
        overlap = len(wa & wb) / min(len(wa), len(wb))
        return overlap >= (same_ratio / 2 if adjacent else same_ratio)

    merged: list[dict] = []
    for s in slides:
        if len((s.get("text") or "").split()) < min_words:
            continue
        if merged and same(merged[-1]["text"], s["text"], adjacent=(s["start"] - merged[-1]["end"] <= 20.0)):
            merged[-1]["end"] = s["end"]
            if len(s["text"]) > len(merged[-1]["text"]):
                merged[-1]["text"] = s["text"]        # keep the fullest reading of the card
                merged[-1]["lines"] = s.get("lines") or merged[-1]["lines"]
            continue
        merged.append({"t": s["start"], "end": s["end"], "text": s["text"], "lines": s.get("lines") or []})
    cards = [c for c in merged if c["end"] - c["t"] >= min_hold_s or len(c["text"].split()) >= strong_words]

    # A hall has its own standing slide, the centre's name or a diagram, and puts it up between acts.
    # A title card names one act and is shown once; a slide that comes back later in the evening is
    # not a title card, however handsome it looks.
    for c in cards:
        c["_repeats"] = sum(1 for other in cards if other is not c and same(other["text"], c["text"], adjacent=True))

    if limit is not None and len(cards) > limit:
        ranked = sorted(cards, key=lambda c: _titleness(c) - 6.0 * c["_repeats"], reverse=True)
        cards = sorted(ranked[:limit], key=lambda c: c["t"])
    for c in cards:
        c.pop("_repeats", None)
    return cards
