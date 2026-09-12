"""Transcribe spoken segments (introductions) with faster-whisper, in-process or via another interpreter."""
from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from .config import Config
from .fusion import Segment

WORKER = r'''
import json, sys
from faster_whisper import WhisperModel
job = json.load(open(sys.argv[1]))
model = WhisperModel(job["model"], device=job["device"], compute_type="float16" if job["device"] == "cuda" else "int8")
out = []
for item in job["items"]:
    segs, info = model.transcribe(item["wav"], language=job["language"], vad_filter=True, beam_size=5,
                                  condition_on_previous_text=False)
    parts = [{"start": round(s.start + item["offset"], 2), "end": round(s.end + item["offset"], 2),
              "text": s.text.strip(), "p_no_speech": round(s.no_speech_prob, 3)} for s in segs]
    out.append({"id": item["id"], "language": info.language, "parts": parts})
json.dump(out, open(job["out"], "w"), ensure_ascii=False)
'''


def transcribe_segments(wav: Path, sr_hint: int, segments: list[Segment], out_dir: Path, cfg: Config,
                        python: str | None = None, log=print) -> dict[int, dict]:
    """Return {segment_index: {"text", "parts", "language"}} for speech segments. Cached as transcripts.json."""
    cache = out_dir / "transcripts.json"
    store = json.loads(cache.read_text()) if cache.exists() else {}      # keyed by "start-end" so re-segmenting reuses work
    key = lambda s: f"{s.start:.1f}-{s.end:.1f}"
    idx = [i for i, s in enumerate(segments) if s.kind == "speech" and key(s) not in store]
    if not idx:
        return {i: store[key(s)] for i, s in enumerate(segments) if s.kind == "speech" and key(s) in store}
    y, fs = sf.read(str(wav), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    tmp = Path(tempfile.mkdtemp(prefix="cs_whisper_"))
    items = []
    for i in idx:
        s = segments[i]
        clip = y[int(s.start * fs): int(s.end * fs)]
        p = tmp / f"seg_{i:03d}.wav"
        sf.write(str(p), clip, fs)
        items.append({"id": i, "wav": str(p), "offset": s.start})
    device = "cuda" if cfg.device in ("auto", "cuda") else "cpu"
    if device == "cuda":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            pass
    job = {"model": cfg.whisper_model, "language": cfg.whisper_language, "device": device,
           "items": items, "out": str(tmp / "out.json")}
    job_path = tmp / "job.json"; job_path.write_text(json.dumps(job))
    worker = tmp / "worker.py"; worker.write_text(WORKER)
    interpreters = [python] if python else []
    interpreters.append(sys.executable)
    result = None
    for exe in interpreters:
        try:
            subprocess.run([exe, str(worker), str(job_path)], check=True, capture_output=True, text=True)
            result = json.loads(Path(job["out"]).read_text())
            break
        except subprocess.CalledProcessError as e:
            log(f"  whisper via {exe} failed: {e.stderr.strip().splitlines()[-1] if e.stderr else e}")
    if result is None:
        log("  transcription skipped (faster-whisper not available)")
        return {i: store[key(s)] for i, s in enumerate(segments) if s.kind == "speech" and key(s) in store}
    for r in result:
        parts = [p for p in r["parts"] if p["p_no_speech"] < 0.8 and p["text"]]
        store[key(segments[r["id"]])] = {"language": r["language"], "text": " ".join(p["text"] for p in parts), "parts": parts}
    cache.write_text(json.dumps(store, ensure_ascii=False, indent=1))
    return {i: store[key(s)] for i, s in enumerate(segments) if s.kind == "speech" and key(s) in store}


def from_full_transcript(full: dict, segments: list[Segment]) -> dict[int, dict]:
    """Attach the parts of a whole-file Whisper transcript to the speech segments they fall in."""
    out = {}
    parts = [p for p in full.get("segments", []) if p.get("text") and p.get("p_no_speech", p.get("no_speech_prob", 0)) < 0.8]
    for i, s in enumerate(segments):
        if s.kind != "speech":
            continue
        mine = [p for p in parts if p["end"] > s.start and p["start"] < s.end]
        out[i] = {"language": full.get("language"), "text": " ".join(p["text"].strip() for p in mine), "parts": mine}
    return out


def attach_transcript_to_turns(full: dict, turns: list[dict]) -> None:
    """Give each speaker turn the transcript text that overlaps it (in place)."""
    parts = [p for p in full.get("segments", []) if p.get("text")]
    j = 0
    for t in turns:
        txt = []
        for p in parts:
            if p["end"] <= t["start"]:
                continue
            if p["start"] >= t["end"]:
                break
            ov = min(p["end"], t["end"]) - max(p["start"], t["start"])
            if ov >= 0.5 * (p["end"] - p["start"]) or ov >= 1.0:
                txt.append(p["text"].strip())
        t["text"] = " ".join(txt)
