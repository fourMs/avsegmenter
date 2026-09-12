"""Frame-wise AudioSet tagging with PANNs CNN14 through ``ambiscape.ml.tag_frames`` (cached)."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .config import Config

PANNS_SR = 32000


def tag_frames(y: np.ndarray, sr: int, out_dir: Path, cfg: Config, log=print) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (T, P, labels): window centres in seconds, (n_frames, 527) posteriors, AudioSet label names."""
    cache = out_dir / "panns_frames.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        if float(z["win"]) == cfg.win_s and float(z["hop"]) == cfg.hop_s:
            return z["T"], z["P"], list(z["labels"])
    from ambiscape import ml
    log(f"  tagging {len(y) / sr / 60:.0f} min on {ml.resolve_device(cfg.device)}")
    T, P, labels = ml.tag_frames(np.asarray(y), sr, win_s=cfg.win_s, hop_s=cfg.hop_s, device=cfg.device)
    np.savez(cache, T=T, P=P.astype(np.float32), labels=np.array(labels), win=cfg.win_s, hop=cfg.hop_s)
    return T, P, list(labels)
