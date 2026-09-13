"""Research layers: generic time-series tracks and annotation tiers, kept apart from the dissemination view.

The record gets an additive ``research`` block::

    research: {
      tracks: [{id, label, kind: "curve"|"state"|"image", unit, hop_s, values | states | image, source, note}],
      tiers:  [{id, label, kind: "interval"|"point", source, items: [{start, end, label, attrs, confidence}]}]
    }

The analysis fills it from what it already computed (level, quantity of motion, camera state, videogram
and motiongram images, every structural layer as a tier). Researchers add their own with
``avsegmenter add-track`` (CSV: time,value) and ``avsegmenter add-tier`` (ELAN .eaf, an ELAN
tab-separated export, or CSV with start,end,label); both merge into the record with provenance and
survive re-runs because they are stored in ``research_additions.json``, which the analysis only reads.
"""
from __future__ import annotations
import csv
import datetime as _dt
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

ADDITIONS = "research_additions.json"


def _r(x, n=3):
    return None if x is None else round(float(x), n)


# ---------------------------------------------------------------- built from the analysis
def builtin_tracks(d: dict, out_dir: Path) -> list[dict]:
    tr = d.get("tracks") or {}
    out = []
    if tr.get("level_db"):
        out.append({"id": "level_db", "label": "Level (RMS)", "kind": "curve", "unit": "dBFS", "hop_s": tr.get("hop_s", 1.0),
                    "values": tr["level_db"], "source": "avsegmenter.audio.rms_db", "range": [-60, 0]})
    if tr.get("qom"):
        out.append({"id": "qom", "label": "Quantity of motion (camera-still frames)", "kind": "curve", "unit": "share of concert max",
                    "hop_s": tr.get("hop_s", 1.0), "values": tr["qom"], "source": "musicalgestures.extract_tracks (qom.f4), camera motion masked",
                    "range": [0, 1]})
    cam = d.get("camera")
    if cam and (out_dir / "camera.json").exists():
        c = json.loads((out_dir / "camera.json").read_text())
        out.append({"id": "camera_state", "label": "Camera", "kind": "state", "hop_s": c["hop_s"], "states": c["state"],
                    "palette": {"still": "#94a3b8", "moving": "#f59e0b", "cut": "#ef4444"}, "source": "musicalgestures.camera_motion"})
        if c.get("tx"):
            out.append({"id": "camera_pan", "label": "Camera pan (px per sample)", "kind": "curve", "unit": "px", "hop_s": c["hop_s"],
                        "values": c["tx"], "source": "musicalgestures.camera_motion", "range": [-10, 10]})
    sp = d.get("speakers")
    if sp and sp.get("turns"):
        hop = 1.0; n = int(d["video"]["duration"] // hop) + 1
        states = [None] * n
        for t in sp["turns"]:
            for i in range(int(t["start"] // hop), min(n, int(t["end"] // hop) + 1)):
                states[i] = t["speaker"]
        out.append({"id": "speaker", "label": "Speaker", "kind": "state", "hop_s": hop, "states": states, "source": "avsegmenter.speakers"})
    if d.get("videogram"):
        out.append({"id": "videogram", "label": "Videogram", "kind": "image", "image": d["videogram"], "source": "musicalgestures videograms"})
    if (out_dir / "motiongram.png").exists():
        out.append({"id": "motiongram", "label": "Motiongram", "kind": "image", "image": "motiongram.png", "source": "musicalgestures.extract_tracks"})
    return out


def builtin_tiers(d: dict) -> list[dict]:
    tiers = []
    tiers.append({"id": "segments", "label": "Segments", "kind": "interval", "source": "avsegmenter.fusion (PANNs)",
                  "items": [{"start": s["start"], "end": s["end"], "label": s["kind"], "confidence": s.get("confidence"),
                             "attrs": {"title": s.get("title")}} for s in d["segments"]]})
    if d.get("pieces"):
        tiers.append({"id": "pieces", "label": "Pieces", "kind": "interval", "source": "avsegmenter.pipeline",
                      "items": [{"start": p["start"], "end": p["end"], "label": p["title"],
                                 "attrs": {"index": p["index"], "ensemble": p.get("ensemble"), "instruments": [i["label"] for i in p.get("instruments") or []][:4],
                                           "people": (p.get("performers") or {}).get("estimate"), "tempo_bpm": (p.get("music") or {}).get("tempo_bpm"),
                                           "key": (p.get("music") or {}).get("key")}} for p in d["pieces"]]})
    if d.get("parts"):
        tiers.append({"id": "parts", "label": "Parts", "kind": "interval", "source": "avsegmenter.parts",
                      "items": [{"start": p["start"], "end": p["end"], "label": p.get("title") or p["kind"],
                                 "attrs": {"kind": p["kind"], "cues": p.get("cues"), "content_share": p.get("content_share")}} for p in d["parts"]]})
    sp = d.get("speakers")
    if sp and sp.get("turns"):
        names = {k: (v.get("name") or k) for k, v in (sp.get("speakers") or {}).items()}
        tiers.append({"id": "turns", "label": "Speaker turns", "kind": "interval", "source": "avsegmenter.speakers (ECAPA)",
                      "items": [{"start": t["start"], "end": t["end"], "label": names.get(t["speaker"], t["speaker"]),
                                 "attrs": {"speaker": t["speaker"], "text": t.get("text")}} for t in sp["turns"]]})
    cam = d.get("camera") or {}
    if cam.get("cuts"):
        tiers.append({"id": "cuts", "label": "Camera cuts", "kind": "point", "source": "musicalgestures.camera_motion",
                      "items": [{"start": c, "end": c, "label": "cut"} for c in cam["cuts"]]})
    pts = [{"start": b, "end": b, "label": f"novelty in piece {p['index']}"} for p in d.get("pieces") or [] for b in p.get("sub_boundaries") or []]
    if pts:
        tiers.append({"id": "novelty", "label": "Novelty peaks (ambiscape)", "kind": "point", "source": "ambiscape.segmentation.segment", "items": pts})
    cues = [{"start": c["t"], "end": c["t"], "label": c["why"], "attrs": {"piece": p["index"]}} for p in d.get("pieces") or [] for c in p.get("internal_cues") or []]
    if cues:
        tiers.append({"id": "cues", "label": "Song-change cues", "kind": "point", "source": "avsegmenter.pipeline.internal_cues", "items": cues})
    return tiers


# ---------------------------------------------------------------- importers
def read_eaf(path: Path) -> list[dict]:
    """ELAN .eaf: one tier dict per TIER, times from TIME_ORDER (ms)."""
    root = ET.parse(str(path)).getroot()
    slots = {ts.get("TIME_SLOT_ID"): int(ts.get("TIME_VALUE")) / 1000.0 for ts in root.iter("TIME_SLOT") if ts.get("TIME_VALUE") is not None}
    tiers = []
    for tier in root.iter("TIER"):
        items = []
        for a in tier.iter("ALIGNABLE_ANNOTATION"):
            t1, t2 = slots.get(a.get("TIME_SLOT_REF1")), slots.get(a.get("TIME_SLOT_REF2"))
            if t1 is None or t2 is None:
                continue
            val = (a.findtext("ANNOTATION_VALUE") or "").strip()
            items.append({"start": _r(t1), "end": _r(t2), "label": val})
        tiers.append({"id": re.sub(r"\W+", "_", tier.get("TIER_ID", "tier")).strip("_").lower(), "label": tier.get("TIER_ID"),
                      "kind": "interval", "source": f"ELAN {Path(path).name}", "items": sorted(items, key=lambda x: x["start"])})
    return tiers


def _to_seconds(v: str) -> float:
    v = v.strip()
    if re.match(r"^\d+:\d\d:\d\d(\.\d+)?$", v):
        h, m, s = v.split(":"); return int(h) * 3600 + int(m) * 60 + float(s)
    if re.match(r"^\d+:\d\d(\.\d+)?$", v):
        m, s = v.split(":"); return int(m) * 60 + float(s)
    return float(v.replace(",", "."))


def read_elan_csv(path: Path) -> list[dict]:
    """ELAN's tab-separated export (tier, begin, end, duration, annotation) or a plain CSV with start,end,label[,tier]."""
    text = Path(path).read_text(encoding="utf-8-sig")
    dialect = csv.excel_tab if text.count("\t") > text.count(",") else csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return None
    has_header = col("start", "begin", "begin time - ss.msec", "begin time") is not None
    body = rows[1:] if has_header else rows
    ci = {"tier": col("tier", "tier name"), "start": col("start", "begin", "begin time - ss.msec", "begin time - hh:mm:ss.ms", "begin time"),
          "end": col("end", "end time - ss.msec", "end time - hh:mm:ss.ms", "end time"), "label": col("label", "annotation", "value", "text")}
    if ci["start"] is None:
        ci = {"tier": None, "start": 0, "end": 1, "label": 2}
    tiers: dict[str, list] = {}
    for r in body:
        if len(r) <= max(v for v in ci.values() if v is not None):
            continue
        name = r[ci["tier"]].strip() if ci["tier"] is not None else Path(path).stem
        try:
            a = _to_seconds(r[ci["start"]]); b = _to_seconds(r[ci["end"]]) if ci["end"] is not None else a
        except ValueError:
            continue
        tiers.setdefault(name, []).append({"start": _r(a), "end": _r(b), "label": r[ci["label"]].strip() if ci["label"] is not None and ci["label"] < len(r) else ""})
    return [{"id": re.sub(r"\W+", "_", n).strip("_").lower(), "label": n, "kind": "interval" if any(i["end"] > i["start"] for i in items) else "point",
             "source": f"{Path(path).name}", "items": sorted(items, key=lambda x: x["start"])} for n, items in tiers.items()]


def read_track_csv(path: Path) -> tuple[list[float], list[float]]:
    """CSV with time,value (header optional; time in seconds or h:mm:ss)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    dialect = csv.excel_tab if text.count("\t") > text.count(",") else csv.excel
    times, values = [], []
    for r in csv.reader(text.splitlines(), dialect):
        if len(r) < 2:
            continue
        try:
            times.append(_to_seconds(r[0])); values.append(float(r[1].replace(",", ".")))
        except ValueError:
            continue
    return times, values


# ---------------------------------------------------------------- additions on disk
def load_additions(out_dir: Path) -> dict:
    p = Path(out_dir) / ADDITIONS
    return json.loads(p.read_text()) if p.exists() else {"tracks": [], "tiers": []}


def save_additions(out_dir: Path, add: dict) -> None:
    (Path(out_dir) / ADDITIONS).write_text(json.dumps(add, ensure_ascii=False, indent=1))


def add_tier(out_dir: Path, path: Path, tier_id: str | None = None, label: str | None = None, author: str | None = None) -> list[str]:
    path = Path(path)
    tiers = read_eaf(path) if path.suffix.lower() == ".eaf" else read_elan_csv(path)
    if tier_id and len(tiers) == 1:
        tiers[0]["id"] = tier_id
    if label and len(tiers) == 1:
        tiers[0]["label"] = label
    add = load_additions(out_dir)
    ids = []
    for t in tiers:
        t["added"] = _dt.datetime.now().isoformat(timespec="seconds"); t["author"] = author
        add["tiers"] = [x for x in add["tiers"] if x["id"] != t["id"]] + [t]; ids.append(t["id"])
    save_additions(out_dir, add)
    return ids


def add_track(out_dir: Path, path: Path, track_id: str, label: str | None = None, unit: str | None = None, hop_s: float = 1.0,
              author: str | None = None) -> str:
    """Resample an irregular time,value CSV onto a regular grid (nearest sample) and store it."""
    times, values = read_track_csv(path)
    if not times:
        raise ValueError(f"no time,value rows in {path}")
    import numpy as np
    t = np.asarray(times); v = np.asarray(values)
    order = np.argsort(t); t, v = t[order], v[order]
    grid = np.arange(0, t[-1] + hop_s, hop_s)
    res = np.interp(grid, t, v)
    add = load_additions(out_dir)
    track = {"id": track_id, "label": label or track_id, "kind": "curve", "unit": unit, "hop_s": hop_s,
             "values": [round(float(x), 4) for x in res], "source": f"{Path(path).name}", "added": _dt.datetime.now().isoformat(timespec="seconds"), "author": author}
    add["tracks"] = [x for x in add["tracks"] if x["id"] != track_id] + [track]
    save_additions(out_dir, add)
    return track_id


def research_block(d: dict, out_dir: Path) -> dict:
    add = load_additions(out_dir)
    tracks = builtin_tracks(d, out_dir) + add.get("tracks", [])
    tiers = builtin_tiers(d) + add.get("tiers", [])
    return {"tracks": tracks, "tiers": tiers, "additions_file": ADDITIONS,
            "note": "tracks: regular series (curve/state) or image strips; tiers: interval or point annotations. Builtin entries are recomputed on every run; entries from research_additions.json are kept as they are."}


def motiongram_png(analysis_dir: Path, out_png: Path, max_columns: int = 2000) -> Path | None:
    """The MGT motiongram strip (motion-frame means) for the research view."""
    try:
        from musicalgestures._tracks import read_columns
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cols, _ = read_columns(str(analysis_dir), max_columns=max_columns, which="motiongram_v")
        img = np.asarray(cols).T.astype(float)
        hi = np.percentile(img, 99.5) or 1.0
        plt.imsave(str(out_png), np.clip(img / hi, 0, 1) ** 0.5, cmap="gray", vmin=0, vmax=1)
        return out_png
    except Exception:
        return None
