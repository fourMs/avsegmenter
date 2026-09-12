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


def raised_stage(detections: dict, min_conf: float = 0.5, min_height: float = 0.3) -> bool:
    """Does the picture have a raised stage? Yes when most of the large, confident person boxes have their heads in
    the upper half of the frame (performers on a stage seen from the hall); no when they sit low (a lecture hall
    filmed from the back, a slide capture with the speakers along the bottom)."""
    import numpy as np
    ys = [b[1] for f in detections.get("frames", []) for b in f["boxes"] if b[4] >= min_conf and (b[3] - b[1]) >= min_height]
    return bool(ys) and float(np.mean(np.asarray(ys) <= 0.5)) >= 0.5


def use_stage_filter(cfg: Config, detections: dict | None) -> bool:
    if cfg.stage_filter in (True, False):
        return bool(cfg.stage_filter)
    return raised_stage(detections) if detections else True


def performer_counts(detections: dict, seg: Segment, cfg: Config, cam: dict | None = None, kind: str = "piece") -> dict:
    """MGT's ``performer_count`` per still framing (else the percentile rule). A *piece* counts the widest framing
    (everyone is on stage at some point); a *part* of talk counts the typical framing (the widest framings of a
    lecture are the hall and the slides). The audience filter is on when the detections show a raised stage."""
    geo = {} if use_stage_filter(cfg, detections) else {"head_below": 1.0, "cut_head_below": 1.0}
    c = performer_count(detections, seg.start, seg.end, camera=cam, min_conf=cfg.person_conf,
                        stat="widest" if kind == "piece" else "typical", **geo)
    return {"estimate": c["estimate"], "low": c.get("low"), "high": c.get("high", c["max"]), "frames": c["frames"],
            "framings": c.get("framings"), "method": c["method"], "stage_filter": not geo}
