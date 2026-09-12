"""Camera cuts and PTZ: ``musicalgestures._camera`` on the videogram proxy, cached as camera.json."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from musicalgestures._camera import camera_motion, camera_state_at as state_at, still_runs  # noqa: F401


def analyse_camera(proxy: Path, out_dir: Path, log=print) -> dict | None:
    if not proxy.exists():
        return None
    return camera_motion(proxy, proxy_path=proxy, cache=out_dir / "camera.json", verbose=False)


def piece_camera(cam: dict, start: float, end: float) -> dict:
    if not cam:
        return {}
    tt = np.asarray(cam["t"]); st = np.asarray(cam["state"], dtype=object)
    sel = (tt >= start) & (tt < end)
    n = int(sel.sum())
    shots = [s for s in cam["shots"] if s["end"] > start and s["start"] < end]
    return {"shots": len(shots), "cuts": [c for c in cam["cuts"] if start <= c < end],
            "framings": len(still_runs(cam, start, end)),
            "moving_share": round(float((st[sel] == "moving").mean()), 3) if n else None,
            "still_share": round(float((st[sel] == "still").mean()), 3) if n else None}
