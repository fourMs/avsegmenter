"""The canonical record: automatic analysis merged with the curated overlay, in five layers.

Merge rule: everything in ``curated.json`` wins over the automatic values, field by field; automatic
values that the curator has not touched stay, and the record says for every curated field that a
person set it (``provenance.curated``). The analysis never writes ``curated.json``.
"""
from __future__ import annotations
import datetime as _dt
import hashlib
import json
from pathlib import Path

from . import vocab

RECORD_SCHEMA_VERSION = "1.0"


def load_curated(analysis_dir: Path) -> dict:
    """``curated.json`` (new name) or ``metadata.json`` (what the pipeline has used so far)."""
    for name in ("curated.json", "metadata.json"):
        p = Path(analysis_dir) / name
        if p.exists():
            return json.loads(p.read_text())
    return {}


def sha256(path: Path, block: int = 1 << 22) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def _people(d: dict, curated: dict) -> list[dict]:
    """Contributors with roles: from curated ``people`` first, else from the plan and the speakers."""
    out = []
    for p in curated.get("people", []):
        out.append({"name": p["name"], "role": p.get("role", "performer"), "affiliation": p.get("affiliation"),
                    "identifier": p.get("identifier"), "source": "curated"})
    if out:
        return out
    seen = set()
    for pc in d.get("pieces") or []:
        pl = pc.get("plan") or {}
        for name in [n.strip() for n in (pl.get("performers") or "").replace(" og ", ",").split(",") if n.strip() and n.strip() not in ("–", "-")]:
            if name not in seen:
                seen.add(name); out.append({"name": name, "role": "performer", "source": "programme"})
        comp = (pl.get("composer") or "").strip()
        if comp and comp not in seen and comp not in ("–", "-") and comp != pl.get("performers"):
            seen.add(comp); out.append({"name": comp, "role": "composer", "source": "programme"})
    for sid, st in ((d.get("speakers") or {}).get("speakers") or {}).items():
        name = st.get("name")
        if name and name not in seen:
            seen.add(name)
            role = (st.get("role") or "").split("/")[0].strip() or "speaker"
            out.append({"name": name, "role": {"main": "presenter", "host": "presenter", "speaker": "presenter"}.get(role, "presenter"), "source": "curated-speakers"})
    return out


def build_record(analysis_dir: Path, video_path: Path | None = None, base_url: str | None = None,
                 identifier: str | None = None, with_checksum: bool = True, urn_prefix: str | None = None) -> dict:
    """The canonical record. ``urn_prefix`` (or ``curated.json: urn_prefix``) namespaces the local identifiers,
    e.g. ``urn:uio:imv``; the default is ``urn:avsegmenter``."""
    A = Path(analysis_dir)
    d = json.loads((A / "segments.json").read_text())
    curated = load_curated(A)
    prefix = urn_prefix or curated.get("urn_prefix") or vocab.DEFAULT_URN_PREFIX
    tech = (d.get("video") or {}).get("tech") or {}
    video_file = d["video"]["file"]
    video_path = Path(video_path) if video_path else (A.parent / video_file)
    ident = identifier or curated.get("identifier") or f"{prefix}:recording:{Path(video_file).stem}"
    desc = curated.get("description") or d.get("title")
    date = curated.get("date") or (tech.get("created") or "")[:10] or None
    profile = d.get("profile", "concert")
    items = []
    for pt in d.get("parts") or []:
        items.append({"kind": pt["kind"], "index": pt.get("index"), "title": pt.get("title"), "start": pt["start"], "end": pt["end"],
                      "speakers": pt.get("speakers"), "people_on_stage": (pt.get("performers") or {}).get("estimate"),
                      "camera": pt.get("camera"), "plan": pt.get("plan"), "pieces": pt.get("pieces")})
    for pc in d.get("pieces") or []:
        items.append({"kind": "piece", "index": pc["index"], "title": pc["title"], "start": pc["start"], "end": pc["end"],
                      "part_index": pc.get("part_index"),
                      "plan": pc.get("plan"), "performers": pc.get("performers"), "ensemble": pc.get("ensemble"),
                      "instruments": [dict(i, **vocab.audioset_term(i["label"])) for i in pc.get("instruments") or []],
                      "genres": [dict(g, **vocab.audioset_term(g["label"])) for g in pc.get("genres") or []],
                      "music": pc.get("music"), "camera": pc.get("camera"), "intro": pc.get("intro"),
                      "rights": pc.get("rights")})
    segments = [{"id": s["id"], "kind": s["kind"], "kind_id": vocab.segment_class_id(s["kind"], prefix),
                 "audioset": vocab.audioset_term(vocab.SEGMENT_CLASS_LABELS[s["kind"]][0]) if s["kind"] in vocab.SEGMENT_CLASS_LABELS else None,
                 "start": s["start"], "end": s["end"], "confidence": s.get("confidence"), "title": s.get("title"),
                 "transcript": s.get("transcript"), "thumbnail": s.get("thumbnail")} for s in d["segments"]]
    turns = [{"start": t["start"], "end": t["end"], "speaker": t["speaker"], "text": t.get("text")} for t in ((d.get("speakers") or {}).get("turns") or [])]
    speakers = {k: {"name": v.get("name"), "role": v.get("role"), "total_s": v.get("total_s")} for k, v in (((d.get("speakers") or {}).get("speakers")) or {}).items()}
    cam = d.get("camera") or {}
    meta = d.get("metadata") or {}
    rights = {
        "license": curated.get("license") or meta.get("license"), "license_url": curated.get("license_url") or meta.get("license_url"),
        "rights_holder": curated.get("rights_holder") or meta.get("rights_holder"),
        "privacy": meta.get("privacy") or curated.get("privacy"),
        "works": meta.get("copyrights") or [], "notes": meta.get("notes") or curated.get("notes"),
        "access": curated.get("access") or "restricted",   # restricted until a person says otherwise
        "embargo_until": curated.get("embargo_until"),
    }
    tools = d.get("tools") or {}
    provenance = {
        "generated": d.get("generated"), "record_built": _dt.datetime.now().isoformat(timespec="seconds"),
        "software": [{"name": "avsegmenter", "version": __import__("avsegmenter").__version__},
                     {"name": "musicalgestures", "version": tools.get("musicalgestures")},
                     {"name": "ambiscape", "version": tools.get("ambiscape")}, {"name": "musiscape", "version": tools.get("musiscape")}],
        "models": [{"name": "PANNs CNN14 (AudioSet)", "use": "segment classes, instruments, genres"},
                   {"name": "YOLO11n", "use": "people on stage"}, {"name": "faster-whisper large-v3", "use": "transcripts"},
                   {"name": "speechbrain ECAPA-TDNN", "use": "speaker turns"} if turns else None],
        "parameters": d.get("config"), "profile": profile,
        "curated_fields": sorted(k for k in curated.keys()),
        "automatic_layers": ["structural", "technical", "descriptive:auto"], "curated_layers": ["rights", "descriptive:curated"],
    }
    provenance["models"] = [m for m in provenance["models"] if m]
    return {
        "schema": f"urn:avsegmenter:record:{RECORD_SCHEMA_VERSION}", "identifier": ident, "urn_prefix": prefix, "base_url": base_url,
        "descriptive": {"title": curated.get("title") or d.get("title"), "description": desc, "date": date,
                        "venue": curated.get("venue"), "organisation": curated.get("organisation"), "organisation_url": curated.get("organisation_url"),
                        "event_type": profile, "genre": vocab.PROFILE_GENRE.get(profile), "language": curated.get("language") or ((d.get("speakers") or {}).get("language")),
                        "people": _people(d, curated), "keywords": curated.get("keywords", [])},
        "technical": {**tech, "sha256": sha256(video_path) if with_checksum else None, "duration_s": d["video"]["duration"], "path": str(video_path)},
        "structural": {"items": items, "segments": segments, "turns": turns, "speakers": speakers,
                       "camera": {"cuts": cam.get("cuts"), "summary": cam.get("summary"), "n_shots": cam.get("n_shots"),
                                  "terms": vocab.CAMERA_STATE_TERMS, "scheme": vocab.MPEG7_CAMERA} if cam else None,
                       "tracks": {"level_db_1hz": (d.get("tracks") or {}).get("level_db")}, "videogram": d.get("videogram")},
        "rights": rights, "provenance": provenance,
        "files": {"segments": "segments.json", "player": "player.html", "chapters": "chapters.vtt", "videogram": d.get("videogram"), "thumbnails": "thumbs/"},
    }
