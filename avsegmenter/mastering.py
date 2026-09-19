"""Cut the parts of a recording out as files, with the loudness treatment each part deserves.

Speech and music want opposite things. Several people sharing one microphone in a room arrive at
different levels, and the difference is a defect: on one PhD defence the four voices spanned 10.9 LU,
and 4 to 7 LU of that sat inside a single part. The cure is a leveller slow enough to even one
speaker against the next, a true-peak limiter for the isolated bangs, and then one gain to the
target. Music arrives with its dynamics intact, and those dynamics are the content, so it is given
the gain and a limiter that should never engage, and nothing else. A crescendo is not a defect.

Why the limiter comes before the measurement: a recording of a room has a crest factor of 30 dB or
more, and ``loudnorm`` asked for a target it cannot reach with a plain gain, because that gain would
put the peaks over the ceiling, falls back to a dynamic mode of its own without reporting it. Taking
the peaks first is what lets the loudness step stay linear.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Loudness smoothed over 31 frames of 200 ms, about 6 s, so the gain follows a speaker rather than
#: a syllable. 2 s and 10 s both left the voices further apart on the recording this was tuned on.
LEVELLER = "highpass=f=70,dynaudnorm=f=200:g=31:p=0.9:m=12:r=0.9"


@dataclass(frozen=True)
class Target:
    """Where the file should land. -16 LUFS is the web figure; broadcast delivery is -23."""
    i: float = -16.0
    tp: float = -1.5
    lra: float = 11.0

    def limit(self) -> str:
        """``alimiter`` takes a linear ceiling, not decibels."""
        return f"{10 ** (self.tp / 20):.4f}"


def music_share(part: dict, segments: list[dict]) -> float:
    """How much of a part is music, by duration."""
    span = max(0.0, float(part["end"]) - float(part["start"]))
    if span <= 0:
        return 0.0
    played = sum(min(float(s["end"]), float(part["end"])) - max(float(s["start"]), float(part["start"]))
                 for s in segments if s.get("kind") == "music"
                 and float(s["end"]) > float(part["start"]) and float(s["start"]) < float(part["end"]))
    return max(0.0, min(1.0, played / span))


def treatment(part: dict, segments: list[dict], music_max: float = 0.2) -> str:
    """``"talk"`` for a part that is mostly speech, ``"music"`` for one that is not.

    The threshold is generous on purpose: the demonstrations inside a lecture are music by class and
    are not a reason to stop levelling the voices around them.
    """
    return "music" if music_share(part, segments) > music_max else "talk"


def prefilter(kind: str, target: Target = Target()) -> str:
    """The filters in front of the loudness step, for a part of this kind."""
    lim = f"alimiter=limit={target.limit()}:level=false"
    return f"{LEVELLER},{lim}" if kind == "talk" else lim


def _loudnorm(target: Target, measured: dict | None = None) -> str:
    base = f"loudnorm=I={target.i}:TP={target.tp}:LRA={target.lra}"
    if measured is None:
        return base + ":print_format=json"
    return (base + f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")


def measure_command(video: Path, start: float, end: float, pre: str, target: Target = Target()) -> list[str]:
    """First pass: what the span measures once the filters in front of the loudness step have run."""
    return ["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.2f}", "-to", f"{end:.2f}",
            "-i", str(video), "-vn", "-af", f"{pre},{_loudnorm(target)}", "-f", "null", "-"]


def cut_command(video: Path, start: float, end: float, pre: str, measured: dict, out: Path,
                target: Target = Target(), hwaccel: bool = True, crf_args: list[str] | None = None) -> list[str]:
    """Second pass: the cut, with one gain to the target.

    ``-hwaccel``, ``-ss`` and ``-to`` are input options and go before ``-i``; after it ffmpeg reads
    them as output options and stops.
    """
    enc = crf_args or ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "32",
                       "-b:v", "1200k", "-maxrate", "3M", "-bufsize", "6M"]
    return (["ffmpeg", "-hide_banner", "-v", "error", "-y"]
            + (["-hwaccel", "cuda"] if hwaccel else [])
            + ["-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(video)] + enc
            + ["-af", f"{pre},{_loudnorm(target, measured)}", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(out)])


def parse_measurement(stderr: str) -> dict:
    """The JSON block ``loudnorm`` prints at the end of the measuring pass."""
    a, b = stderr.rfind("{"), stderr.rfind("}")
    if a < 0 or b < a:
        raise ValueError("loudnorm printed no measurement")
    return json.loads(stderr[a:b + 1])


def slug(text: str, fallback: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in (text or "").lower())
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-")[:48] or fallback


def cut_parts(analysis_dir: Path, video: Path, out_dir: Path, target: Target = Target(),
              pad_s: float = 0.0, stem: str = "", hwaccel: bool = True, log=print) -> dict:
    """One file per part, each measured and then brought to the target. Returns the index written
    beside them as ``parts.json``. A part already on disk is left alone, so the call reruns."""
    data = json.loads((analysis_dir / "segments.json").read_text())
    segments, duration = data["segments"], float(data["video"]["duration"])
    parts = [p for p in (data.get("parts") or []) if p.get("kind") == "part"]
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    for p in parts:
        nr = p.get("index")
        kind = treatment(p, segments)
        start, end = max(0.0, float(p["start"]) - pad_s), min(duration, float(p["end"]) + pad_s)
        name = f"{nr}-{stem + '-' if stem else ''}{slug(p.get('title') or '', f'part-{nr}')}.mp4"
        pre = prefilter(kind, target)
        entry = {"part": nr, "title": p.get("title", ""), "treatment": kind,
                 "music_share": round(music_share(p, segments), 3),
                 "start_s": round(start, 2), "end_s": round(end, 2), "duration_s": round(end - start, 2)}
        out = out_dir / name
        if out.exists():
            log(f"  {name} already on disk")
            index[name] = entry
            continue
        r = subprocess.run(measure_command(video, start, end, pre, target), capture_output=True, text=True, check=True)
        m = parse_measurement(r.stderr)
        entry["measured_lufs"] = float(m["input_i"])
        log(f"  {name}: {kind}, measured {m['input_i']} LUFS, range {m['input_lra']} LU")
        subprocess.run(cut_command(video, start, end, pre, m, out, target, hwaccel), check=True)
        index[name] = entry
    (out_dir / "parts.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    return index
