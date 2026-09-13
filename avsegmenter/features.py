"""Standard low-level features as 1 Hz tracks: audio descriptors with their MPEG-7 names, colour and
brightness of the picture, and motion-vector quantity of motion from the codec (MGT, PyAV).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

MPEG7 = {"centroid_hz": "AudioSpectrumCentroid", "bandwidth_hz": "AudioSpectrumSpread", "flatness": "AudioSpectrumFlatness",
         "rolloff_hz": None, "zcr": None, "onset_rate": None, "power_db": "AudioPower"}


def audio_descriptors(y22: np.ndarray, sr: int, out_dir: Path) -> dict:
    """Spectral centroid, bandwidth, flatness, rolloff, zero-crossing rate and onset rate, one value per second
    (median of the 512-hop frames), cached as audio_features.json."""
    cache = Path(out_dir) / "audio_features.json"
    if cache.exists():
        return json.loads(cache.read_text())
    import librosa
    y = np.asarray(y22, dtype=np.float32); hop = 512; fps = sr / hop
    n = int(len(y) / sr) + 1
    chunk_s = 600                                                     # bounded memory for hours-long recordings
    per = {k: [] for k in ("centroid_hz", "bandwidth_hz", "flatness", "rolloff_hz", "zcr")}
    onset_rate = []
    for c0 in range(0, len(y), chunk_s * sr):
        seg = y[c0: c0 + chunk_s * sr]
        if len(seg) < sr:
            per_sec = 0
        S = np.abs(librosa.stft(seg, n_fft=2048, hop_length=hop))
        feats = {"centroid_hz": librosa.feature.spectral_centroid(S=S, sr=sr)[0], "bandwidth_hz": librosa.feature.spectral_bandwidth(S=S, sr=sr)[0],
                 "flatness": librosa.feature.spectral_flatness(S=S)[0], "rolloff_hz": librosa.feature.spectral_rolloff(S=S, sr=sr)[0],
                 "zcr": librosa.feature.zero_crossing_rate(seg, frame_length=2048, hop_length=hop)[0]}
        onset_env = librosa.onset.onset_strength(S=librosa.power_to_db(S ** 2), sr=sr, hop_length=hop)
        onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, units="time")
        secs = int(np.ceil(len(seg) / sr))
        for k, v in feats.items():
            per[k] += [round(float(np.median(v[int(i * fps): int((i + 1) * fps)])), 4) if int((i + 1) * fps) <= len(v) else None for i in range(secs)]
        onset_rate += [int(((onsets >= i) & (onsets < i + 1)).sum()) for i in range(secs)]
        del S
    out = {"hop_s": 1.0, "tracks": {k: v[:n] for k, v in per.items()}}
    out["tracks"]["onset_rate"] = onset_rate[:n]
    out["mpeg7"] = MPEG7
    cache.write_text(json.dumps(out)); return out


def picture_colour(proxy: Path, out_dir: Path, hop_s: float = 1.0) -> dict:
    """Mean brightness (V) and saturation (S) per second, and a per-minute dominant-hue palette strip
    (colourgram.png) from the proxy video, in the spirit of MPEG-7 ColorLayout / DominantColor."""
    cache = Path(out_dir) / "picture_colour.json"
    if cache.exists():
        return json.loads(cache.read_text())
    import cv2
    cap = cv2.VideoCapture(str(proxy)); fps = cap.get(cv2.CAP_PROP_FPS) or 2.0
    step = max(1, int(round(fps * hop_s)))
    bright, sat, hues, minute_hist = [], [], [], []
    i = 0; acc = np.zeros(18)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            hsv = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2HSV)
            bright.append(round(float(hsv[..., 2].mean()) / 255, 4)); sat.append(round(float(hsv[..., 1].mean()) / 255, 4))
            h = np.bincount((hsv[..., 0].ravel() // 10).astype(int), minlength=18)[:18] * (hsv[..., 1].ravel() > 40).mean()
            acc += h
            if len(bright) % 60 == 0:
                minute_hist.append((acc / max(1, acc.sum())).round(4).tolist()); acc = np.zeros(18)
        i += 1
    cap.release()
    if acc.sum() > 0:
        minute_hist.append((acc / acc.sum()).round(4).tolist())
    # palette strip: one column per minute, rows = 18 hue bins weighted by share
    if minute_hist:
        H = np.array(minute_hist).T  # (18, minutes)
        img = np.zeros((18, H.shape[1], 3), np.uint8)
        for b in range(18):
            hsv = np.uint8([[[b * 10 + 5, 200, 255]]]); rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]
            for m in range(H.shape[1]):
                img[b, m] = (rgb * min(1.0, H[b, m] * 4)).astype(np.uint8)
        cv2.imwrite(str(Path(out_dir) / "colourgram.png"), cv2.cvtColor(cv2.resize(img, (max(200, H.shape[1] * 4), 72), interpolation=cv2.INTER_NEAREST), cv2.COLOR_RGB2BGR))
    out = {"hop_s": hop_s, "brightness": bright, "saturation": sat, "hue_hist_per_minute": minute_hist,
           "image": "colourgram.png" if minute_hist else None, "mpeg7": ["ColorLayout", "DominantColor"], "source": "avsegmenter.features.picture_colour (proxy)"}
    cache.write_text(json.dumps(out)); return out


def motion_vectors(video: Path, out_dir: Path, budget_pixel_frames: float, pixel_frames: float) -> dict | None:
    """Codec motion vectors via MGT (PyAV): magnitude per frame folded to 1 Hz, plus the share of frames with
    coherent global motion (camera) from the median vector. Skipped above the budget."""
    cache = Path(out_dir) / "motion_vectors.json"
    if cache.exists():
        return json.loads(cache.read_text())
    if pixel_frames > budget_pixel_frames:
        return None
    try:
        import musicalgestures as mg
        d = mg.MgVideo(str(video)).motionvectordata()          # per decoded frame: time, picture_type, magnitude, median dx/dy
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    keep = np.asarray(d.picture_type) == "P"                     # B-frame vectors span varying distances; P-frames track QoM at r = 0.87
    t = np.asarray(d.time, float)[keep]; mag = np.asarray(d.magnitude, float)[keep]
    mdx = np.asarray(d.median_dx, float)[keep]; mdy = np.asarray(d.median_dy, float)[keep]
    n = int(t.max()) + 1 if len(t) else 0
    per, glob = [], []
    for i in range(n):
        m = (t >= i) & (t < i + 1)
        per.append(round(float(np.nanmean(mag[m])), 4) if m.any() else None)
        glob.append(round(float(np.hypot(np.nanmedian(mdx[m]), np.nanmedian(mdy[m]))), 4) if m.any() else None)
    out = {"hop_s": 1.0, "magnitude": per, "global_motion": glob, "source": "musicalgestures._motionvectors.accumulate_motion_vectors (codec vectors, P-frames)",
           "mpeg7": "MotionActivity"}
    cache.write_text(json.dumps(out)); return out


def captions_vtt(transcript_parts: list[dict], out_path: Path) -> Path | None:
    """WebVTT captions from transcript parts ({start, end, text})."""
    parts = [p for p in transcript_parts if p.get("text")]
    if not parts:
        return None
    def ts(t):
        t = max(0.0, float(t)); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    lines = ["WEBVTT", ""]
    for k, p in enumerate(sorted(parts, key=lambda x: x["start"]), 1):
        lines += [str(k), f"{ts(p['start'])} --> {ts(max(p['end'], p['start'] + 0.5))}", p["text"].strip(), ""]
    Path(out_path).write_text("\n".join(lines)); return Path(out_path)
