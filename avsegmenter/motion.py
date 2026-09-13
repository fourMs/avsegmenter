"""Video side via MGT: motion tracks (QoM, videograms) for the timeline, keyframe thumbnails per segment."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
import numpy as np
from .fusion import Segment


def motion_tracks(video: Path, out_dir: Path, workers: int | None = None, log=print) -> Path | None:
    """musicalgestures.extract_tracks_parallel -> analysis dir with qom.f4, videogram_*.u1, tracks.json (cached)."""
    from musicalgestures._tracks import extract_tracks_parallel
    mgt_dir = out_dir / "mgt"
    existing = list(mgt_dir.glob("*/tracks.json"))
    if existing:
        return existing[0].parent
    try:
        extract_tracks_parallel(str(video), out_dir=str(mgt_dir), workers=workers, chunk_s=120.0)  # returns tracks.json meta
    except Exception as e:
        log(f"  MGT motion tracks skipped: {e}")
        return None
    found = list(mgt_dir.glob("*/tracks.json"))
    return found[0].parent if found else None


def ensure_pyramid(analysis_dir: Path) -> None:
    """read_columns expects decimated levels (videogram_v.L1.u1, ...) for long recordings."""
    from musicalgestures._tracks import build_pyramid
    if not list(analysis_dir.glob("videogram_v.L1.u1")):
        build_pyramid(str(analysis_dir), which="videogram_v")


def qom_per_second(analysis_dir: Path) -> np.ndarray:
    meta = json.loads((analysis_dir / "tracks.json").read_text())
    q = np.memmap(analysis_dir / "qom.f4", dtype=np.float32, mode="r")
    fps = int(round(meta["fps"]))
    n = len(q) // fps
    qs = np.asarray(q[: n * fps]).reshape(n, fps).mean(axis=1)
    return qs


def mask_camera(qs: np.ndarray, cam: dict | None) -> np.ndarray:
    """QoM per second with camera moves and cuts set to NaN (they are camera motion, not performer motion)."""
    q = np.asarray(qs, dtype=float).copy()
    if not cam:
        return q
    from .camera import state_at
    st = state_at(cam, np.arange(len(q)) + 0.5)
    st2 = state_at(cam, np.arange(len(q)) + 0.0)
    q[(st != "still") | (st2 != "still")] = np.nan
    return q


def segment_motion(qs: np.ndarray, seg: Segment) -> dict:
    a, b = int(seg.start), int(min(seg.end, len(qs)))
    if b <= a:
        return {}
    v = qs[a:b]; v = v[np.isfinite(v)]
    ref = np.nanpercentile(qs, 99) or 1.0
    if not v.size:
        return {"qom_mean_norm": None, "qom_p90_norm": None, "still_seconds": 0}
    return {"qom_mean_norm": round(float(v.mean() / ref), 3), "qom_p90_norm": round(float(np.percentile(v, 90) / ref), 3),
            "still_seconds": int(v.size)}


def videogram_png(video: Path, out_dir: Path, out_png: Path, fps: float = 2.0, height: int = 180, log=print,
                  analysis_dir: Path | None = None) -> Path | None:
    """A true videogram of the whole recording as a wide PNG.

    When MGT motion tracks exist (`analysis_dir` with a ``videogram_v`` key in tracks.json, written by
    musicalgestures >= the #383 fix) the columns come straight from ``read_columns``; otherwise the video
    is reduced to ``fps`` frames per second and ``height`` pixels once (proxy_videogram.mp4, also used for
    the camera analysis) and MGT's ``videograms()`` is taken of the proxy."""
    if out_png.exists():
        return out_png
    if analysis_dir is not None:
        try:
            import json
            from musicalgestures._tracks import read_columns
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            meta = json.loads((Path(analysis_dir) / "tracks.json").read_text())
            if "videogram_v" in meta and "motiongram_v" in meta:
                cols, _ = read_columns(str(analysis_dir), max_columns=2000, which="videogram_v")
                plt.imsave(str(out_png), np.asarray(cols).T, cmap="gray", vmin=0, vmax=255)
                return out_png
        except Exception as e:  # noqa: BLE001
            log(f"  videogram from tracks skipped: {e}")
    proxy = out_dir / "proxy_videogram.mp4"
    if not proxy.exists():
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={fps},scale=-2:{height}", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(proxy)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            log(f"  videogram proxy failed: {e.stderr.decode(errors='ignore')[-200:]}")
            return None
    try:
        from musicalgestures import MgVideo
        import cv2
        v = MgVideo(str(proxy))
        v.videograms(target_name_x=str(out_dir / "videogram_x.png"), target_name_y=str(out_dir / "videogram_y.png"), overwrite=True)
        cands = [out_dir / "videogram_x.png", out_dir / "videogram_y.png"]
        imgs = [(c, cv2.imread(str(c))) for c in cands if c.exists()]
        wide = max((ci for ci in imgs if ci[1] is not None), key=lambda ci: ci[1].shape[1] / ci[1].shape[0], default=None)
        if wide is None:
            return None
        cv2.imwrite(str(out_png), wide[1])
        return out_png
    except Exception as e:  # noqa: BLE001
        log(f"  MGT videogram skipped: {e}")
        return None


def thumbnail(video: Path, t: float, out_png: Path, width: int = 320) -> Path | None:
    if out_png.exists():
        return out_png
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
           "-vf", f"scale={width}:-2", str(out_png)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out_png
    except subprocess.CalledProcessError:
        return None
