"""How many people perform in each segment: ``musicalgestures`` person detection with its stage filter."""
from __future__ import annotations
import json
from pathlib import Path
from musicalgestures._performers import detect_people, performer_count
from .config import Config
from .fusion import Segment


def detect_persons(video: Path, out_dir: Path, cfg: Config, log=print) -> dict:
    """Cached ``detect_people`` result (persons.json). An older list-shaped cache is wrapped."""
    cache = out_dir / "persons.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return {"fps": cfg.person_fps, "frames": d} if isinstance(d, list) else d
    d = detect_people(video, fps=cfg.person_fps, verbose=False,
                      device=None if cfg.device == "auto" else (0 if cfg.device == "cuda" else "cpu"))
    cache.write_text(json.dumps(d))
    return d


def performer_counts(detections: dict, seg: Segment, cfg: Config, cam: dict | None = None) -> dict:
    """MGT's ``performer_count``: per still framing when camera analysis is available, else the percentile rule.
    Concerts count the widest framing (everyone is on stage at some point); the talk profile counts the
    typical framing and switches the raised-stage audience filter off (lecture halls, slide captures)."""
    geo = {} if cfg.stage_filter else {"head_below": 1.0, "cut_head_below": 1.0}
    c = performer_count(detections, seg.start, seg.end, camera=cam, min_conf=cfg.person_conf,
                        stat="typical" if cfg.profile == "talk" else "widest", **geo)
    return {"estimate": c["estimate"], "low": c.get("low"), "high": c.get("high", c["max"]), "frames": c["frames"],
            "framings": c.get("framings"), "method": c["method"]}
