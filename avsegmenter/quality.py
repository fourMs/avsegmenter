"""Broadcast-style loudness and quality control, from ffmpeg's analysis filters.

- Loudness per EBU R128 (``ebur128``): integrated LUFS, loudness range (LU), true peak (dBTP), and the
  momentary loudness as a 1 Hz track.
- QC items in the spirit of EBU Tech 3363: black frames (``blackdetect``), frozen picture
  (``freezedetect``), silence (``silencedetect``), audio clipping and DC offset (``astats``), plus what
  ffprobe already tells (dropped/duplicated frame counts are not available without a reference and are
  reported as "not measured").

Everything is a plain dict that lands in the record's ``quality`` block, in EBUCore technical attributes,
and as one PREMIS "quality control" event with per-item outcomes.
"""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def loudness(audio_wav: Path, out_dir: Path) -> dict:
    """EBU R128 summary and momentary loudness at 1 Hz (median of the 10 Hz readings per second)."""
    cache = Path(out_dir) / "loudness.json"
    if cache.exists():
        return json.loads(cache.read_text())
    err = _run(["ffmpeg", "-nostats", "-v", "info", "-i", str(audio_wav), "-af", "ebur128=peak=true", "-f", "null", "-"])
    mom: dict[int, list[float]] = {}
    for m in re.finditer(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)", err):
        t, v = float(m.group(1)), m.group(2)
        if v != "-inf":
            mom.setdefault(int(t), []).append(float(v))
    n = (max(mom) + 1) if mom else 0
    momentary = [round(sorted(mom[i])[len(mom[i]) // 2], 1) if i in mom else None for i in range(n)]
    momentary = [None if (v is None or v < -120) else v for v in momentary]        # digital silence reads as -inf-ish
    tail = err[err.rfind("Summary:"):] if "Summary:" in err else err        # the final block, not the running readings
    def grab(pat):
        m = re.findall(pat, tail); return float(m[-1]) if m else None
    summary = {"integrated_lufs": grab(r"I:\s*(-?[\d.]+) LUFS"), "loudness_range_lu": grab(r"LRA:\s*(-?[\d.]+) LU"),
               "true_peak_dbtp": grab(r"Peak:\s*(-?[\d.]+) dBFS"), "standard": "EBU R128 (ITU-R BS.1770-4)",
               "momentary_lufs_1hz": momentary}
    cache.write_text(json.dumps(summary)); return summary


def qc(video: Path, audio_wav: Path, out_dir: Path, ffmpeg_input_args: list[str] | None = None, max_s: float | None = None) -> dict:
    """QC items with outcomes: black, frozen, silence, clipping, DC offset. Video checks run on the file itself
    (pass ``ffmpeg_input_args`` such as ``["-hwaccel", "cuda"]`` for long files); audio checks on the wav."""
    cache = Path(out_dir) / "qc.json"
    if cache.exists():
        return json.loads(cache.read_text())
    lim = ["-t", str(max_s)] if max_s else []
    verr = _run(["ffmpeg", "-nostats", "-v", "info", *(ffmpeg_input_args or []), "-i", str(video), *lim, "-an",
                 "-vf", "blackdetect=d=1.0:pic_th=0.98,freezedetect=n=-60dB:d=5", "-f", "null", "-"])
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", verr)]
    freeze = [float(x) for x in re.findall(r"lavfi\.freezedetect\.freeze_start: ([\d.]+)", verr)]
    aerr = _run(["ffmpeg", "-nostats", "-v", "info", "-i", str(audio_wav), "-af", "silencedetect=n=-50dB:d=3,astats=measure_overall=Peak_level+Flat_factor+Peak_count+DC_offset:measure_perchannel=none", "-f", "null", "-"])
    silences = [(float(a), float(b)) for a, b in zip(re.findall(r"silence_start: ([\d.]+)", aerr), re.findall(r"silence_end: ([\d.]+)", aerr))]
    def grab(pat):
        m = re.search(pat, aerr); return float(m.group(1)) if m else None
    peak, flat, clips, dc = grab(r"Peak level dB:\s*(-?[\d.]+)"), grab(r"Flat factor:\s*([\d.]+)"), grab(r"Peak count:\s*([\d.]+)"), grab(r"DC offset:\s*(-?[\d.]+)")
    dur = None
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip())
    except ValueError:
        pass
    items = [
        {"id": "black_frames", "label": "Black picture (>= 1 s)", "outcome": "pass" if not black else "warning", "count": len(black),
         "spans": black[:50], "note": "expected at head/tail only" if black else None},
        {"id": "frozen_picture", "label": "Frozen picture (>= 5 s)", "outcome": "pass" if not freeze else "warning", "count": len(freeze), "starts": freeze[:50]},
        {"id": "silence", "label": "Silence >= 3 s below -50 dBFS", "outcome": "info", "count": len(silences), "spans": silences[:100],
         "note": "breaks and pauses are expected in a recording of an event"},
        {"id": "clipping", "label": "Audio clipping", "outcome": "warning" if (peak is not None and peak > -0.5 and (clips or 0) > 100) else "pass",
         "peak_level_db": peak, "flat_factor": flat, "peak_count": clips, "note": "peak level above -0.5 dBFS with repeated full-scale samples counts as clipping"},
        {"id": "dc_offset", "label": "DC offset", "outcome": "pass" if dc is None or abs(dc) < 0.01 else "warning", "value": dc},
        {"id": "frame_integrity", "label": "Dropped / duplicated frames", "outcome": "not measured", "note": "needs a reference or camera log"},
    ]
    if dur and black:
        head = [b for b in black if b[0] < 1.0]; tail = [b for b in black if b[1] > dur - 1.0]
        if len(black) == len(head) + len(tail):
            items[0]["outcome"] = "pass"; items[0]["note"] = "only at head/tail"
    out = {"standard": "EBU Tech 3363 QC items (subset), measured with ffmpeg filters", "items": items,
           "tools": {"ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split()[2]}}
    cache.write_text(json.dumps(out)); return out
