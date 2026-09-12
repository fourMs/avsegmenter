"""Segments from frame-wise AudioSet posteriors: a thin layer over ``musiscape.tagging``.

The chain itself (group max, weighted decision, majority filter, minimum durations, absorbing
'other' beside music, snapping to the song finder, onset refinement) lives upstream in musiscape.
Here it is driven with cached posteriors and mapped onto this package's vocabulary.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import numpy as np
from musiscape import tagging as tg
from .config import Config

KINDS = ("music", "speech", "applause", "silence", "other")
_TO_KIND = {"music": "music", "voices": "speech", "applause": "applause", "quiet": "silence", "other": "other"}
_TO_MS = {v: k for k, v in _TO_KIND.items()}


@dataclass
class Segment:
    start: float
    end: float
    kind: str
    confidence: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        d["start"] = round(self.start, 2); d["end"] = round(self.end, 2)
        d["confidence"] = round(self.confidence, 3)
        return d


def group_scores(P: np.ndarray, labels: list[str]) -> dict[str, np.ndarray]:
    """Group scores in this package's kind names."""
    g = tg.group_scores(P, labels)
    return {_TO_KIND[k]: v for k, v in g.items()}


def fuse(P: np.ndarray, T: np.ndarray, labels: list[str], level_db_frames: np.ndarray, duration: float,
         cfg: Config, songs: list[dict] | None = None, y: np.ndarray | None = None, sr: int | None = None) -> list[Segment]:
    scores = tg.group_scores(P, labels)
    weights = {_TO_MS[k]: w for k, w in cfg.weights.items()}
    lab = tg.mode_filter(tg.decide_frames(scores, level_db_frames, weights, cfg.silence_db, cfg.other_floor), cfg.smooth_frames)
    spans = tg.runs_to_spans(lab, cfg.hop_s, cfg.win_s, duration, scores)
    spans = tg.enforce_min_duration(spans, {_TO_MS[k]: v for k, v in cfg.min_duration_s.items()})
    spans = tg.absorb_other(spans)
    if songs:
        spans = tg.snap_to_songs(spans, songs, cfg.snap_s)
    if y is not None and sr:
        spans = tg.refine_music_onsets(spans, y, sr)
    segs = []
    for s in spans:
        sel = (T >= s["start_s"]) & (T < s["end_s"])
        conf = float(scores[s["label"]][sel].mean()) if sel.any() and s["label"] in scores else s["confidence"]
        segs.append(Segment(s["start_s"], s["end_s"], _TO_KIND[s["label"]], conf))
    return segs
