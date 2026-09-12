"""Describe each musical piece: instruments, genre, singing, ensemble hints (PANNs aggregates)."""
from __future__ import annotations
import re
import numpy as np
from .config import INSTRUMENT_LABELS, GENRE_LABELS
from .fusion import Segment


def _agg(P, T, labels, seg, wanted, top, floor):
    ix = {l: i for i, l in enumerate(labels)}
    sel = (T >= seg.start) & (T < seg.end)
    if not sel.any():
        return []
    mean = P[sel].mean(axis=0)
    rows = [(w, float(mean[ix[w]])) for w in wanted if w in ix]
    rows.sort(key=lambda r: -r[1])
    return [{"label": l, "p": round(p, 3)} for l, p in rows[:top] if p >= floor]


def tag_summary(P: np.ndarray, T: np.ndarray, labels: list[str], seg: Segment) -> dict:
    ix = {l: i for i, l in enumerate(labels)}
    sel = (T >= seg.start) & (T < seg.end)
    mean = P[sel].mean(axis=0) if sel.any() else np.zeros(len(labels))
    top = np.argsort(mean)[::-1][:8]
    return {
        "instruments": _agg(P, T, labels, seg, INSTRUMENT_LABELS, 6, 0.08),
        "genres": _agg(P, T, labels, seg, GENRE_LABELS, 4, 0.04),
        "singing_p": round(float(max(mean[ix["Singing"]], mean[ix["Choir"]], mean[ix["A capella"]])), 3),
        "music_p": round(float(mean[ix["Music"]]), 3),
        "top_tags": [{"label": labels[i], "p": round(float(mean[i]), 3)} for i in top],
    }


def ensemble_hint(instruments: list[dict], singing_p: float, performers: dict | None) -> str:
    names = {i["label"] for i in instruments[:4]}
    n = (performers or {}).get("estimate")
    if "Choir" in names or ("A capella" in names and (n or 0) >= 6):
        return "choir"
    if n is not None and n >= 3 and ({"Drum kit", "Bass guitar", "Electric guitar"} & names):
        return "band"
    if n == 1 or (n is None and len(names) <= 2):
        if "Piano" in names or "Keyboard (musical)" in names:
            return "solo piano"
        if "Synthesizer" in names or "Sampler" in names or "Drum machine" in names:
            return "solo electronics"
        if "Guitar" in names or "Acoustic guitar" in names or "Electric guitar" in names:
            return "solo guitar"
        return "solo"
    if n == 2:
        return "duo"
    if n is not None and n >= 3:
        return f"ensemble ({n})"
    return "unknown"


_NAME = r"([A-ZÆØÅ][\wæøåé\-]+(?:\s+[A-ZÆØÅ][\wæøåé\-]+){0,3})"
_PATTERNS = [
    re.compile(r"\b(?:ved|med|fra|høre)\s+" + _NAME),
    re.compile(r"(?i:vær så god|velkommen),?\s+" + _NAME),
    re.compile(r"(?i:band|duo|trio|kor|koret)\s+(?:som heter\s+)?" + _NAME),
]
_STOP = {"Og", "Så", "Da", "Nå", "Det", "Den", "Vi", "Jeg", "Men", "Her", "Neste", "Dette", "Takk", "Tusen",
         "Ja", "Nei", "Ok", "Hvis", "Når", "For", "Til", "Velkommen", "Konsert", "Konserten"}


def performer_guess(intro_text: str | None) -> list[str]:
    """Names mentioned in the spoken introduction ('... ved Ola Nordmann, vær så god'). A hint, not a fact."""
    if not intro_text:
        return []
    from .programme import thanked_names
    skip = thanked_names(intro_text)
    found = []
    for pat in _PATTERNS:
        for m in pat.finditer(intro_text):
            name = m.group(1).strip()
            words = []
            for w in name.split():
                if w in _STOP:
                    break
                words.append(w)
            cand = " ".join(words)
            if cand.split() and cand.split()[0].lower() in skip:
                continue
            if len(cand) >= 4 and any(ch.islower() for ch in cand) and cand not in found:
                found.append(cand)
    return found[-4:]      # in order of appearance; the last one is normally the act being introduced
