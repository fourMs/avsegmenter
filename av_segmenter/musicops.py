"""musiscape: independent song finder / region classifier, per-piece descriptors, timeline figure."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .fusion import Segment

MS_SR = 22050


def musiscape_songs(wav: Path, out_dir: Path, log=print) -> list[dict]:
    from musiscape import concert
    cache = out_dir / "musiscape_songs.json"
    if cache.exists():
        return json.loads(cache.read_text())
    songs = concert.find_songs([wav], sr=MS_SR, hop_s=1.0, min_song_s=60.0, min_gap_s=12.0)
    cache.write_text(json.dumps(songs, indent=1))
    return songs


def musiscape_regions(y22: np.ndarray, out_dir: Path) -> tuple[list[dict], np.ndarray]:
    """Per-second heuristic labels (music/applause/voices/quiet/other) and level dB, musiscape's own view."""
    from musiscape import concert
    cache = out_dir / "musiscape_regions.json"
    lvl_cache = out_dir / "musiscape_level_db.npy"
    if cache.exists() and lvl_cache.exists():
        return json.loads(cache.read_text()), np.load(lvl_cache)
    labels = concert.classify_regions(y22, MS_SR, hop_s=1.0)
    spans = concert.regions(labels, hop_s=1.0, min_s=5.0)
    level = np.asarray(concert.region_features(y22, MS_SR, hop_s=1.0)["db"], float)
    cache.write_text(json.dumps(spans, indent=1)); np.save(lvl_cache, level)
    return spans, level


def piece_descriptors(y22: np.ndarray, seg: Segment) -> dict:
    """musiscape whole-track descriptors for one piece (key, tempo, pulse clarity, dynamics...)."""
    from musiscape.features import extract_track
    clip = np.asarray(y22[int(seg.start * MS_SR): int(seg.end * MS_SR)], dtype=np.float32)
    if len(clip) < MS_SR * 5:
        return {}
    d = extract_track(clip, MS_SR)
    keep = ["tempo_bpm", "pulse_R", "pulse_bpm", "key", "key_conf", "key_agreement", "tempo_agreement",
            "onset_rate", "dyn_range_db", "chroma_entropy", "centroid_hz", "flatness", "perc_ratio"]
    out = {}
    for k in keep:
        v = d.get(k)
        if isinstance(v, (np.floating, float)):
            out[k] = None if not np.isfinite(v) else round(float(v), 3)
        elif isinstance(v, (np.integer, int)):
            out[k] = int(v)
        else:
            out[k] = v
    # musiscape's documented validity gates
    out["tempo_reliable"] = bool(out.get("pulse_R") is not None and out["pulse_R"] >= 0.1)
    out["key_reliable"] = bool(out.get("chroma_entropy") is not None and out["chroma_entropy"] < 3.3)
    return out


def timeline_png(segments: list[Segment], total_s: float, out_png: Path, level_db: np.ndarray | None, title: str = "") -> Path:
    """Concert overview strip with musiscape's timeline renderer (labels mapped to its vocabulary)."""
    from musiscape.figures import concert_timeline
    m = {"music": "music", "applause": "applause", "speech": "voices", "silence": "quiet", "other": "other"}
    spans = [{"label": m.get(s.kind, "other"), "start_s": s.start, "end_s": s.end, "duration_s": s.duration} for s in segments]
    concert_timeline(spans, total_s, str(out_png), width_px=1920, height_px=260, title=title, level=level_db)
    return out_png
