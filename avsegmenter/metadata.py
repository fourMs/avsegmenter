"""Technical metadata (ffprobe) and the rights/privacy block of the export."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

PRIVACY_LEVELS = ("green", "yellow", "red")


def probe(video: Path) -> dict:
    """Container, video and audio facts from ffprobe, in a flat dict the page can list."""
    try:
        js = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)],
                                       capture_output=True, text=True, check=True).stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {"file": video.name, "size_bytes": video.stat().st_size if video.exists() else None}
    fmt = js.get("format", {})
    v = next((s for s in js.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in js.get("streams", []) if s.get("codec_type") == "audio"), {})

    def fps(r):
        try:
            n, d = r.split("/"); return round(int(n) / int(d), 3)
        except Exception:
            return None
    pix = v.get("pix_fmt", "")
    depth = v.get("bits_per_raw_sample") or ("10" if "10" in pix else "12" if "12" in pix else "8" if pix else None)
    return {
        "file": video.name, "container": fmt.get("format_long_name") or fmt.get("format_name"),
        "size_bytes": int(fmt["size"]) if fmt.get("size") else video.stat().st_size,
        "duration_s": round(float(fmt["duration"]), 2) if fmt.get("duration") else None,
        "bitrate_kbps": round(int(fmt["bit_rate"]) / 1000) if fmt.get("bit_rate") else None,
        "created": (fmt.get("tags") or {}).get("creation_time"),
        "video_codec": v.get("codec_long_name") or v.get("codec_name"), "profile": v.get("profile"),
        "width": v.get("width"), "height": v.get("height"), "fps": fps(v.get("r_frame_rate", "")),
        "pix_fmt": pix or None, "bit_depth": int(depth) if depth else None,
        "color": ", ".join(x for x in (v.get("color_space"), v.get("color_transfer"), v.get("color_range")) if x) or None,
        "video_bitrate_kbps": round(int(v["bit_rate"]) / 1000) if v.get("bit_rate") else None,
        "audio_codec": a.get("codec_long_name") or a.get("codec_name"), "sample_rate_hz": int(a["sample_rate"]) if a.get("sample_rate") else None,
        "channels": a.get("channels"), "channel_layout": a.get("channel_layout"),
        "audio_bitrate_kbps": round(int(a["bit_rate"]) / 1000) if a.get("bit_rate") else None,
        "audio_bit_depth": a.get("bits_per_raw_sample") or a.get("bits_per_sample") or None,
    }


def load_user_metadata(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text())


def rights_block(pieces: list[dict], user: dict, detections: dict | None) -> dict:
    """License, privacy level and known copyrights: what the user states, filled in from the analysis.

    Copyrights start as one entry per planned act (work, composer, performers) with status "unknown";
    a user file can override by plan number (``{"copyrights": [{"nr": "3", "status": "public domain", ...}]}``)
    or add entries without a number. Privacy defaults to a suggestion with its reasons; set it explicitly."""
    # copyrights from the programme and fingerprints
    auto = {}
    for p in pieces:
        pl = p.get("plan") or {}
        key = str(pl.get("nr") or p["id"])
        hits = ((p.get("rights") or {}).get("acoustid_match")) or []
        auto[key] = {"nr": pl.get("nr"), "piece": p["index"], "work": pl.get("work") or None, "composer": pl.get("composer") or None,
                     "performers": pl.get("performers") or None, "status": "unknown",
                     "note": ("fingerprint matched a released recording: " + "; ".join(f"{h.get('title')} – {', '.join(h.get('artists') or [])}" for h in hits[:2])) if hits else None,
                     "source": "programme" if pl else "detected"}
    for entry in user.get("copyrights", []):
        key = str(entry.get("nr") or entry.get("piece") or entry.get("work"))
        if key in auto:
            auto[key].update({k: v for k, v in entry.items() if v is not None})
        else:
            auto[key] = {"status": "unknown", "source": "user", **entry}
    copyrights = sorted(auto.values(), key=lambda e: (e.get("piece") is None, e.get("piece") or 0))

    # privacy suggestion
    reasons = []
    if detections and detections.get("frames"):
        from musicalgestures._performers import on_stage
        audience = sum(1 for f in detections["frames"] for b in f["boxes"] if b[4] >= 0.4 and not on_stage(b))
        if audience > 0.02 * len(detections["frames"]):
            reasons.append("audience members are visible in the picture")
    if any(p.get("performer_names_guess") for p in pieces):
        reasons.append("performers are named in the spoken introductions")
    suggested = {"level": "yellow" if reasons else "green", "reasons": reasons, "suggested": True}
    privacy = user.get("privacy")
    if isinstance(privacy, str):
        privacy = {"level": privacy}
    if privacy:
        privacy = {**suggested, **privacy, "suggested": False}
        if privacy.get("level") not in PRIVACY_LEVELS:
            raise ValueError(f"privacy level must be one of {PRIVACY_LEVELS}")
    else:
        privacy = suggested
    return {"license": user.get("license"), "license_url": user.get("license_url"), "rights_holder": user.get("rights_holder"),
            "privacy": privacy, "copyrights": copyrights, "notes": user.get("notes")}


def derivatives(out_dir: Path, data: dict) -> list[dict]:
    """Every derived file in the analysis folder with format, generator and checksum: the self-description a
    deposit needs (PREMIS derivation events, METS file section, IIIF seeAlso all read this list)."""
    import hashlib
    out_dir = Path(out_dir)
    tools = data.get("tools") or {}
    cat = [
        ("segments.json", "application/json", "avsegmenter", "analysis record"),
        ("curated.json", "application/json", "human", "curated overlay"),
        ("research_additions.json", "application/json", "human/other tools", "research additions"),
        ("chapters.vtt", "text/vtt", "avsegmenter", "chapters"), ("captions.vtt", "text/vtt", "faster-whisper via avsegmenter", "captions"),
        ("videogram.png", "image/png", f"musicalgestures {tools.get('musicalgestures')}", "videogram"),
        ("motiongram.png", "image/png", f"musicalgestures {tools.get('musicalgestures')}", "motiongram"),
        ("colourgram.png", "image/png", "avsegmenter.features", "colourgram"), ("timeline.png", "image/png", f"musiscape {tools.get('musiscape')}", "timeline figure"),
        ("panns_frames.npz", "application/octet-stream", f"ambiscape {tools.get('ambiscape')} (PANNs CNN14)", "AudioSet posteriors, 2 s frames"),
        ("camera.json", "application/json", f"musicalgestures {tools.get('musicalgestures')}", "camera states"),
        ("persons.json", "application/json", f"musicalgestures {tools.get('musicalgestures')} (YOLO)", "person boxes, 1 fps"),
        ("speakers.json", "application/json", "avsegmenter.speakers (silero VAD, ECAPA)", "speaker turns"),
        ("loudness.json", "application/json", "ffmpeg ebur128", "EBU R128 loudness"), ("qc.json", "application/json", "ffmpeg filters", "quality control"),
        ("audio_features.json", "application/json", "librosa via avsegmenter", "audio descriptors, 1 Hz"),
        ("picture_colour.json", "application/json", "avsegmenter.features", "picture colour, 1 Hz"),
        ("motion_vectors.json", "application/json", f"musicalgestures {tools.get('musicalgestures')} (PyAV)", "codec motion vectors, 1 Hz"),
        ("whisper_full.json", "application/json", "faster-whisper", "whole-file transcript"), ("transcripts.json", "application/json", "faster-whisper", "transcripts per segment"),
        ("player.html", "text/html", "avsegmenter", "player"), ("report.html", "text/html", "avsegmenter.report", "summary report"),
    ]
    out = []
    for name, mime, gen, role in cat:
        p = out_dir / name
        if not p.exists():
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest() if p.stat().st_size < 200_000_000 else None
        out.append({"path": name, "mimetype": mime, "size_bytes": p.stat().st_size, "sha256": h, "generator": gen, "role": role})
    thumbs = sorted((out_dir / "thumbs").glob("*.jpg")) if (out_dir / "thumbs").exists() else []
    if thumbs:
        out.append({"path": "thumbs/", "mimetype": "image/jpeg", "count": len(thumbs), "size_bytes": sum(t.stat().st_size for t in thumbs), "generator": "ffmpeg via avsegmenter", "role": "keyframes"})
    mgt = list((out_dir / "mgt").glob("*/tracks.json"))
    if mgt:
        d = mgt[0].parent
        out.append({"path": f"mgt/{d.name}/", "mimetype": "application/octet-stream", "generator": f"musicalgestures {tools.get('musicalgestures')}", "role": "motion tracks (qom.f4, motiongram/videogram bases, pyramids)",
                    "size_bytes": sum(f.stat().st_size for f in d.iterdir() if f.is_file())})
    return out
