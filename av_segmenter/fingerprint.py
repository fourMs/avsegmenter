"""Chromaprint fingerprints per piece (ffmpeg) and optional AcoustID lookup.

Fingerprint lookup identifies *recordings*; a live concert performance rarely matches a released
recording, so a miss says nothing about copyright. Treat this stage as a best-effort hint only.
"""
from __future__ import annotations
import json, subprocess, urllib.parse, urllib.request
from pathlib import Path
from .fusion import Segment


def chromaprint(wav: Path, seg: Segment, max_s: float = 120.0) -> str | None:
    dur = min(seg.duration, max_s)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{seg.start:.2f}", "-t", f"{dur:.2f}", "-i", str(wav),
           "-ac", "1", "-ar", "11025", "-f", "chromaprint", "-fp_format", "base64", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return r.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def acoustid_lookup(fp: str, duration_s: float, api_key: str) -> list[dict]:
    data = urllib.parse.urlencode({"client": api_key, "duration": int(duration_s), "fingerprint": fp,
                                   "meta": "recordings releasegroups"}).encode()
    req = urllib.request.Request("https://api.acoustid.org/v2/lookup", data=data)
    with urllib.request.urlopen(req, timeout=20) as resp:
        js = json.loads(resp.read().decode())
    hits = []
    for r in js.get("results", []):
        for rec in r.get("recordings", []) or []:
            hits.append({"score": r.get("score"), "title": rec.get("title"),
                         "artists": [a.get("name") for a in rec.get("artists", []) or []],
                         "mbid": rec.get("id")})
    return hits


def span_key(s: Segment) -> str:
    return f"{s.start:.1f}-{s.end:.1f}"


def fingerprint_pieces(wav: Path, pieces: list[Segment], out_dir: Path, api_key: str | None, log=print) -> dict[str, dict]:
    """{span_key: {"chromaprint", "lookup"}} cached by time span."""
    cache = out_dir / "fingerprints.json"
    out = json.loads(cache.read_text()) if cache.exists() else {}
    for s in pieces:
        i = span_key(s)
        if i in out and (out[i].get("lookup") is not None or not api_key):
            continue
        fp = chromaprint(wav, s)
        entry = {"chromaprint": fp, "lookup": None}
        if fp and api_key:
            try:
                entry["lookup"] = acoustid_lookup(fp, min(s.duration, 120.0), api_key)
            except Exception as e:  # network / key problems must not kill the run
                entry["lookup_error"] = str(e)
        out[i] = entry
    cache.write_text(json.dumps(out))
    return out
