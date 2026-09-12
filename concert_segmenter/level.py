"""1 Hz level/spectral features and novelty boundaries via ambiscape."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .fusion import Segment


def ambiscape_features(wav: Path, out_dir: Path, log=print) -> dict:
    """ambiscape's cached per-second feature dict F for the whole recording, clock rebased to 0 s."""
    import ambiscape as asc
    feat_dir = out_dir / "ambiscape_features"
    sess = asc.open_recording(str(wav))
    paths = asc.extract_session(sess, str(feat_dir), verbose=False)
    F = asc.load_features(paths)
    F = dict(F)
    t0 = float(np.asarray(F["t"])[0])
    for k in ("t", "t_fast", "t_hi", "min_t"):
        if k in F:
            F[k] = np.asarray(F[k], float) - t0
    return F


def slice_features(F: dict, start: float, end: float) -> dict:
    """Sub-dict of F restricted to [start, end) on the 1 Hz clock (only per-second arrays are sliced)."""
    t = np.asarray(F["t"], float)
    sel = (t >= start) & (t < end)
    n = len(t)
    out = {}
    for k, v in F.items():
        a = np.asarray(v)
        if a.ndim >= 1 and a.shape[0] == n:
            out[k] = a[sel]
        else:
            out[k] = v
    return out


def segment_level(F: dict, seg: Segment) -> dict:
    """Level statistics for one segment from ambiscape's fast (8 Hz) dBFS track."""
    tf = np.asarray(F["t_fast"], float)
    db = np.asarray(F["fast_db"], float)
    sel = (tf >= seg.start) & (tf < seg.end)
    if not sel.any():
        return {}
    v = db[sel]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {}
    leq = 10 * np.log10(np.mean(10 ** (v / 10)))
    return {"leq_dbfs": round(float(leq), 1), "l10_dbfs": round(float(np.percentile(v, 90)), 1),
            "l90_dbfs": round(float(np.percentile(v, 10)), 1)}


def sub_boundaries(F: dict, seg: Segment, min_seg_s: float = 45.0, threshold_db: float = 4.0) -> list[float]:
    """Candidate internal boundaries (song changes inside a set, sections inside a piece) from ambiscape novelty."""
    from ambiscape.segmentation import segment as asc_segment
    if seg.duration < 3 * min_seg_s:
        return []
    Fs = slice_features(F, seg.start, seg.end)
    try:
        return [round(float(b), 1) for b in asc_segment(Fs, min_seg_s=min_seg_s, threshold_db=threshold_db)]
    except Exception:
        return []
