"""Audio extraction (MGT) and loading."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa


def extract_audio(video: Path, out_dir: Path) -> Path:
    """Extract a PCM wav next to the outputs using musicalgestures.extract_wav (ffmpeg under the hood)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "audio.wav"
    if target.exists():
        return target
    from musicalgestures._utils import extract_wav
    return Path(extract_wav(str(video), target_name=str(target), overwrite=True))


def load_mono(wav: Path, sr: int) -> tuple[np.ndarray, int]:
    """Mono float32 at the requested rate (cached as <wav>.<sr>.npy)."""
    cache = wav.with_suffix(f".{sr}.npy")
    if cache.exists():
        return np.load(cache, mmap_mode="r"), sr
    y, fs = sf.read(str(wav), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if fs != sr:
        y = librosa.resample(y, orig_sr=fs, target_sr=sr, res_type="soxr_hq")
    np.save(cache, y.astype(np.float32))
    return y, sr


def rms_db(y: np.ndarray, sr: int, hop_s: float) -> np.ndarray:
    hop = int(sr * hop_s)
    n = len(y) // hop
    v = y[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((v.astype(np.float64) ** 2).mean(axis=1)) + 1e-9)
