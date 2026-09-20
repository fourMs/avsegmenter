"""End-to-end: video -> segments -> pieces -> web export."""
from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
import numpy as np

from .captions import load_transcript as load_transcript_cues   # the name 'captions' is taken later in run()
from .config import Config
from . import audio, tagging, fusion, level, musicops, pieces, performers, speech, fingerprint, motion, export, programme, camera, metadata, speakers, parts as partsmod, research, quality, features


def _versions() -> dict:
    v = {}
    for mod in ("musicalgestures", "ambiscape", "musiscape"):
        try:
            v[mod] = __import__(mod).__version__
        except Exception:
            v[mod] = None
    return v


def internal_cues(P, T, labels, db_frames, seg, speech_p=0.3, dip_db=12.0) -> list[dict]:
    """Strong song-change cues inside one music segment: someone talks, or the level drops well below the piece."""
    ix = {l: i for i, l in enumerate(labels)}
    sel = (T >= seg.start + 6) & (T < seg.end - 6)
    if not sel.any():
        return []
    med = float(np.median(db_frames[sel]))
    cues, last = [], -1e9
    for t, sp, db in zip(T[sel], P[sel, ix["Speech"]], db_frames[sel]):
        why = "speech" if sp >= speech_p else ("quiet" if db < med - dip_db else None)
        if why and t - last > 8:
            cues.append({"t": round(float(t), 1), "why": why}); last = t
        elif why:
            last = t
    return cues


def run(video: Path, out_dir: Path, cfg: Config, video_url: str | None = None, title: str | None = None,
        whisper_python: str | None = None, skip: set[str] = frozenset(), programme_path: str | None = None,
        metadata_path: str | None = None, log=print) -> dict:
    video = Path(video).resolve(); out_dir = Path(out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    cfg.for_profile()
    talk = cfg.profile == "talk"
    thumbs = out_dir / "thumbs"; thumbs.mkdir(exist_ok=True)

    log("1/9 audio"); wav = audio.extract_audio(video, out_dir)
    y32, _ = audio.load_mono(wav, tagging.PANNS_SR)
    duration = len(y32) / tagging.PANNS_SR

    log("2/9 PANNs tagging (ambiscape.ml)"); T, P, labels = tagging.tag_frames(y32, tagging.PANNS_SR, out_dir, cfg, log)
    db_frames = np.array([audio.rms_db(np.asarray(y32[int((t - cfg.win_s / 2) * tagging.PANNS_SR): int((t + cfg.win_s / 2) * tagging.PANNS_SR)]),
                                       tagging.PANNS_SR, cfg.win_s)[0] if int((t + cfg.win_s / 2) * tagging.PANNS_SR) <= len(y32) else -99.0
                          for t in T])

    log("3/9 musiscape song finder + region classifier"); songs = musicops.musiscape_songs(wav, out_dir, log)
    y22, _ = audio.load_mono(wav, musicops.MS_SR)
    ms_spans, ms_level = musicops.musiscape_regions(y22, out_dir)

    log("4/9 fuse into segments (musiscape.tagging)"); segs = fusion.fuse(P, T, labels, db_frames, duration, cfg, songs, y=y32, sr=tagging.PANNS_SR)

    log("5/9 ambiscape features (level, novelty)")
    F = None
    try:
        F = level.ambiscape_features(wav, out_dir, log)
    except Exception as e:
        log(f"  ambiscape features skipped: {e}")

    log("6/9 video: performers (YOLO) + MGT motion tracks")
    dets = None if "video" in skip else performers.detect_persons(video, out_dir, cfg, log)
    tech0 = metadata.probe(video)
    pixel_frames = (tech0.get("width") or 1280) * (tech0.get("height") or 720) * (tech0.get("fps") or 25) * duration
    have_tracks = bool(list((out_dir / "mgt").glob("*/tracks.json")))
    if "video" in skip:
        adir = None
    elif have_tracks or pixel_frames <= cfg.motion_budget:
        adir = motion.motion_tracks(video, out_dir, log=log)
    else:
        log(f"  MGT motion tracks skipped: {pixel_frames / 1e9:.0f} G pixel-frames exceeds the budget ({cfg.motion_budget / 1e9:.0f} G); run with --motion-tracks to force")
        adir = None
    qs = motion.qom_per_second(adir) if adir else None
    cam = None
    if "video" not in skip:
        motion.videogram_png(video, out_dir, out_dir / "videogram.png", log=log, analysis_dir=adir)
        from musicalgestures._camera import make_proxy
        make_proxy(video, out_dir / "proxy_videogram.mp4")          # the camera analysis needs the proxy either way
        cam = camera.analyse_camera(out_dir / "proxy_videogram.mp4", out_dir, log=log)
    if qs is not None:
        qs = motion.mask_camera(qs, cam)
    if adir and not (out_dir / "motiongram.png").exists():
        research.motiongram_png(adir, out_dir / "motiongram.png")

    log("7/9 speech transcription")
    full = out_dir / "whisper_full.json"
    if "speech" in skip:
        tr = {}
    elif full.exists():
        tr = speech.from_full_transcript(json.loads(full.read_text()), segs)
    else:
        tr = speech.transcribe_segments(wav, tagging.PANNS_SR, segs, out_dir, cfg, whisper_python, log)

    dia = None
    speech_total = sum(s.duration for s in segs if s.kind == "speech")
    want_dia = cfg.diarize == "always" or (cfg.diarize == "auto" and speech_total >= cfg.diarize_min_speech_s)
    if want_dia and "speakers" not in skip:
        log(f"7b/9 speakers (VAD + ECAPA + clustering) over {speech_total / 60:.0f} min of talk")
        y16, _ = audio.load_mono(wav, speakers.SR)
        dia = speakers.diarize(y16, out_dir, device="cuda" if cfg.device in ("auto", "cuda") else "cpu",
                               threshold=cfg.speaker_threshold, n_speakers=cfg.n_speakers, log=log)
        for t in dia["turns"]:
            t.setdefault("text", "")
        names = metadata.load_user_metadata(metadata_path).get("speakers") or {}
        for sid, st in dia["speakers"].items():
            st["name"] = names.get(sid); st["role"] = dia["roles"].get(sid)
        if full.exists():
            speech.attach_transcript_to_turns(json.loads(full.read_text()), dia["turns"])
        elif tr:
            speech.attach_transcript_to_turns({"segments": [pp for v in tr.values() for pp in v.get("parts", [])]}, dia["turns"])

    log("8/9 describe pieces")
    music_idx = [i for i, s in enumerate(segs) if s.kind == "music"]
    fps = {} if "fingerprint" in skip else fingerprint.fingerprint_pieces(wav, [segs[i] for i in music_idx], out_dir, cfg.acoustid_key, log)

    seg_dicts, piece_dicts = [], []
    for i, s in enumerate(segs):
        d = s.to_dict(); d["id"] = f"seg-{i:03d}"; d.pop("meta", None)
        th = motion.thumbnail(video, s.start + min(10.0, s.duration / 2), thumbs / f"seg-{i:03d}.jpg") if "video" not in skip else None
        d["thumbnail"] = f"thumbs/{th.name}" if th else None
        if F is not None:
            d["level"] = level.segment_level(F, s)
        if qs is not None:
            d["motion"] = motion.segment_motion(qs, s)
        if s.kind == "speech" and i in tr:
            d["transcript"] = tr[i]["text"]
            d["title"] = "Talk: " + (tr[i]["text"][:60] + ("…" if len(tr[i]["text"]) > 60 else "")) if tr[i]["text"] else "Talk"
        elif s.kind == "speech":
            d["title"] = "Talk"
        elif s.kind == "applause":
            d["title"] = "Applause"
        elif s.kind == "silence":
            d["title"] = "Silence / pause"
        elif s.kind == "other":
            d["title"] = "Ambience / other"
        seg_dicts.append(d)

    for n, i in enumerate(music_idx, start=1):
        s = segs[i]; d = seg_dicts[i]
        tags = pieces.tag_summary(P, T, labels, s)
        perf = performers.performer_counts(dets, s, cfg, cam, kind="piece") if dets else None
        # the nearest preceding speech segment (within 5 min) is the spoken introduction
        intro_ids = []
        for j in range(i - 1, -1, -1):
            if segs[j].kind == "music":
                break
            if segs[j].kind == "speech" and s.start - segs[j].end < 600 and tr.get(j, {}).get("text"):
                intro_ids.append(j)
        intro_ids.reverse()
        intro = intro_ids[0] if intro_ids else None
        intro_text = " ".join(tr[j]["text"] for j in intro_ids) if intro_ids else None
        names = pieces.performer_guess(intro_text)
        desc = musicops.piece_descriptors(y22, s)
        fp = fps.get(fingerprint.span_key(s), {})
        hits = fp.get("lookup") or []
        piece = {
            "id": d["id"], "index": n, "start": d["start"], "end": d["end"], "duration": d["duration"],
            "confidence": d["confidence"],
            "title": f"Piece {n}" + (f" – {names[-1]}" if names else ""),
            "performer_names_guess": names,
            "performers": perf,
            "ensemble": pieces.ensemble_hint(tags["instruments"], tags["singing_p"], perf),
            "instruments": tags["instruments"], "genres": tags["genres"], "singing_p": tags["singing_p"],
            "top_tags": tags["top_tags"],
            "music": desc,
            "level": d.get("level"), "motion": d.get("motion"),
            "camera": camera.piece_camera(cam, s.start, s.end) if cam else None,
            "sub_boundaries": level.sub_boundaries(F, s) if F is not None else [],
            "internal_cues": internal_cues(P, T, labels, db_frames, s),
            "intro": {"segment": seg_dicts[intro]["id"], "start": seg_dicts[intro]["start"], "text": intro_text} if intro is not None else None,
            "rights": {
                "fingerprint_computed": bool(fp.get("chromaprint")),
                "acoustid_match": hits[:3],
                "note": ("Matches a released recording; see acoustid_match." if hits else
                         "No released-recording match (expected for a live performance). Rights depend on the work "
                         "and the performers; identify the work from the spoken introduction and the programme."),
            },
            "thumbnail": d["thumbnail"],
        }
        d["title"] = piece["title"]
        d["piece_index"] = n
        piece_dicts.append(piece)

    # ---- parts for every recording: breaks, applause followed by talk, arrival of a major voice
    music_total = sum(s.duration for s in segs if s.kind == "music")
    acts = programme.load_programme(programme_path) if programme_path else []
    acts_to = "pieces" if (piece_dicts and music_total >= speech_total) else "parts"
    # A running order tells the detector how many parts to look for; where the acts belong to the
    # pieces instead, it says nothing about parts and the count is left alone.
    expect = len(acts) if (acts and acts_to == "parts") else None
    parts = partsmod.find_parts(segs, dia["turns"] if dia else [], duration, gap_s=cfg.part_gap_s,
                                min_s=cfg.part_min_s, expect_parts=expect)
    for pt in parts:
        if pt["kind"] == "part":
            pt["speakers"] = speakers.speaker_of(dia["turns"], pt["start"], pt["end"]) if dia else {}
            pt.setdefault("id", f"part-{pt['index']}")          # named here: the alignment below refers to it
    plan = None
    if acts and acts_to == "pieces":
        al = programme.align([{"id": pc["id"], "intro": (pc["intro"] or {}).get("text")} for pc in piece_dicts], acts)
        for pc in piece_dicts:
            j = al["assignments"].get(pc["id"])
            if j is None:
                continue
            a = acts[j]
            act_t = programme.act_title(a)
            work = act_t.split(". ", 1)[1].split(" – ")[0] if ". " in act_t else a.get("work")
            pc["plan"] = {"nr": a.get("nr"), "act": a.get("act"), "work": work, "composer": a.get("composer"),
                          "performers": a.get("performers"), "match": al["how"][pc["id"]],
                          "match_score": round(max(al["scores"][pc["id"]] or [0]), 2)}
            pc["title"] = act_t
            seg_dicts[[d["id"] for d in seg_dicts].index(pc["id"])]["title"] = pc["title"]
        plan = {"source": str(programme_path), "acts": acts, "aligned_to": "pieces", "assignments": al["assignments"],
                "not_detected": [acts[j] | {"index": j} for j in al["not_detected"]]}
    # An act is matched to the part in which it was announced, when the names were caught on the
    # recording. An event often runs in a different order from its announcement, and the words said
    # in the room are the better witness; where no name is heard, the running order still decides.
    part_align = None
    if acts and acts_to == "parts":
        cues = []
        try:
            cues = load_transcript_cues(out_dir)
        except FileNotFoundError:
            cues = []
        if cues:
            real_parts = [pt for pt in parts if pt["kind"] == "part"]
            intros = []
            for pt in real_parts:
                a, b = pt["start"] - 120.0, pt["start"] + 75.0      # the hand-over, then the first words
                text = " ".join((c.get("text") or "").strip() for c in cues if c["end"] > a and c["start"] < b)
                intros.append({"id": pt["id"], "intro": text})
            part_align = programme.align(intros, acts)
    partsmod.title_parts(parts, acts if acts_to == "parts" else [], dia["roles"] if dia else None,
                         assignments=(part_align or {}).get("assignments"))
    if acts and acts_to == "parts":
        if part_align:
            plan = {"source": str(programme_path), "acts": acts, "aligned_to": "parts",
                    "assignments": part_align["assignments"], "how": part_align["how"],
                    "not_detected": [acts[j] | {"index": j} for j in part_align["not_detected"]]}
        else:
            plan = {"source": str(programme_path), "acts": acts, "aligned_to": "parts",
                    "assignments": {f"part-{pt['index']}": acts.index(pt["plan"]) for pt in parts if pt.get("plan")},
                    "not_detected": [a | {"index": j} for j, a in enumerate(acts) if a not in [pt.get("plan") for pt in parts]]}
    for pt in parts:
        if pt["kind"] != "part":
            continue
        pt.setdefault("id", f"part-{pt['index']}")
        if dets:
            pt["performers"] = performers.performer_counts(dets, fusion.Segment(pt["start"], pt["end"], "speech"), cfg, cam, kind="part")
        if cam:
            pt["camera"] = camera.piece_camera(cam, pt["start"], pt["end"])
        pt["pieces"] = [pc["index"] for pc in piece_dicts if pt["start"] <= pc["start"] < pt["end"]]
    for d in seg_dicts:
        for pt in parts:
            if pt["kind"] == "part" and pt["start"] <= d["start"] < pt["end"]:
                d["part_index"] = pt["index"]
    for pc in piece_dicts:
        pc["part_index"] = next((pt["index"] for pt in parts if pt["kind"] == "part" and pt["start"] <= pc["start"] < pt["end"]), None)

    tech = tech0
    user_meta = metadata.load_user_metadata(metadata_path)
    # The language the transcript was actually made in, so the caption track can name it.
    lang = None
    if full.exists():
        lang = json.loads(full.read_text()).get("language")
    elif tr:
        lang = next((v.get("language") for v in tr.values() if v.get("language")), None)

    data = {
        "title": title or video.stem,
        "language": lang,
        "video": {"file": video.name, "duration": round(duration, 2), "url": video_url or video.name,
                  "width": tech.get("width"), "height": tech.get("height"), "tech": tech},
        "metadata": metadata.rights_block(piece_dicts, user_meta, dets),
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "tools": _versions(),
        "config": {"win_s": cfg.win_s, "hop_s": cfg.hop_s, "weights": cfg.weights, "min_duration_s": cfg.min_duration_s},
        "profile": cfg.profile,
        "segments": seg_dicts,
        "pieces": piece_dicts,
        "parts": parts,
        "speakers": ({"speakers": dia["speakers"], "roles": dia["roles"], "turns": dia["turns"]} if dia else None),
        "hierarchy": {"parts": sum(1 for pt in parts if pt["kind"] == "part"), "pieces": len(piece_dicts),
                      "turns": len(dia["turns"]) if dia else 0, "segments": len(seg_dicts), "programme_aligned_to": acts_to if acts else None},
        "tracks": {"hop_s": 1.0,
                   "level_db": [round(float(v), 1) for v in audio.rms_db(np.asarray(y32), tagging.PANNS_SR, 1.0)],
                   "qom": [None if not np.isfinite(v) else round(float(v), 4) for v in (qs / (np.nanpercentile(qs, 99) or 1.0))] if qs is not None else None},
        "camera": {"hop_s": cam["hop_s"], "cuts": cam["cuts"], "summary": cam["summary"], "n_shots": len(cam["shots"])} if cam else None,
        "videogram": "videogram.png" if (out_dir / "videogram.png").exists() else None,
        "musiscape": {"songs": songs, "regions": ms_spans},
        "programme": plan,
        "summary": {k: round(sum(s.duration for s in segs if s.kind == k), 1) for k in fusion.KINDS},
    }
    # ---- broadcast-style quality, standard features, captions, derivatives
    log("8b/9 loudness, QC, standard features")
    hw = ["-hwaccel", "cuda"] if pixel_frames > 2e11 else None
    qual = {"loudness": None, "qc": None}
    if "quality" not in skip:
        try:
            qual["loudness"] = quality.loudness(wav, out_dir)
        except Exception as e:  # noqa: BLE001
            log(f"  loudness skipped: {e}")
        try:
            qual["qc"] = quality.qc(video, wav, out_dir, ffmpeg_input_args=hw)
        except Exception as e:  # noqa: BLE001
            log(f"  qc skipped: {e}")
    feats = {"audio": None, "colour": None, "motion_vectors": None}
    if "features" not in skip:
        try:
            feats["audio"] = features.audio_descriptors(y22, musicops.MS_SR, out_dir)
        except Exception as e:  # noqa: BLE001
            log(f"  audio descriptors skipped: {e}")
        if (out_dir / "proxy_videogram.mp4").exists():
            try:
                feats["colour"] = features.picture_colour(out_dir / "proxy_videogram.mp4", out_dir)
            except Exception as e:  # noqa: BLE001
                log(f"  picture colour skipped: {e}")
        if "video" not in skip:
            feats["motion_vectors"] = features.motion_vectors(video, out_dir, cfg.motion_budget, pixel_frames)
            if feats["motion_vectors"] and feats["motion_vectors"].get("error"):
                log(f"  motion vectors skipped: {feats['motion_vectors']['error'][:120]}"); feats["motion_vectors"] = None
    cap_parts = [pp for v in tr.values() for pp in v.get("parts", [])] if tr else []
    if full.exists():
        cap_parts = [pp for pp in json.loads(full.read_text()).get("segments", []) if pp.get("p_no_speech", 0) < 0.8]
    captions = features.captions_vtt(cap_parts, out_dir / "captions.vtt") if cap_parts else None
    data["quality"] = qual
    data["features"] = {"audio": {k: v for k, v in (feats["audio"] or {}).items() if k != "tracks"} if feats["audio"] else None,
                        "colour": {k: v for k, v in (feats["colour"] or {}).items() if k not in ("brightness", "saturation", "hue_hist_per_minute")} if feats["colour"] else None,
                        "motion_vectors": {k: v for k, v in (feats["motion_vectors"] or {}).items() if k not in ("magnitude", "global_motion")} if feats["motion_vectors"] else None}
    data["captions"] = "captions.vtt" if captions else None
    extra_tracks = []
    if qual["loudness"] and qual["loudness"].get("momentary_lufs_1hz"):
        extra_tracks.append({"id": "loudness_m", "label": "Momentary loudness", "kind": "curve", "unit": "LUFS", "hop_s": 1.0, "values": qual["loudness"]["momentary_lufs_1hz"], "source": "ffmpeg ebur128 (EBU R128)", "range": [-50, -10]})
    if feats["audio"]:
        labels = {"centroid_hz": ("Spectral centroid", "Hz", [0, 5000]), "bandwidth_hz": ("Spectral bandwidth", "Hz", [0, 5000]), "flatness": ("Spectral flatness", "", [0, 0.5]),
                  "rolloff_hz": ("Spectral rolloff", "Hz", [0, 10000]), "zcr": ("Zero-crossing rate", "", [0, 0.3]), "onset_rate": ("Onset rate", "onsets/s", [0, 8])}
        for k, vals in feats["audio"]["tracks"].items():
            lab, unit, rng = labels.get(k, (k, "", None))
            mp = features.MPEG7.get(k)
            extra_tracks.append({"id": k, "label": lab + (f" (MPEG-7 {mp})" if mp else ""), "kind": "curve", "unit": unit, "hop_s": 1.0, "values": vals, "source": "librosa via avsegmenter.features", "range": rng, "mpeg7": mp})
    if feats["colour"]:
        c = feats["colour"]
        extra_tracks.append({"id": "brightness", "label": "Picture brightness", "kind": "curve", "unit": "0..1", "hop_s": c["hop_s"], "values": c["brightness"], "source": c["source"], "range": [0, 1]})
        extra_tracks.append({"id": "saturation", "label": "Picture saturation", "kind": "curve", "unit": "0..1", "hop_s": c["hop_s"], "values": c["saturation"], "source": c["source"], "range": [0, 1]})
        if c.get("image"):
            extra_tracks.append({"id": "colourgram", "label": "Colourgram (dominant hues per minute)", "kind": "image", "image": c["image"], "source": c["source"]})
    if feats["motion_vectors"]:
        mv = feats["motion_vectors"]
        extra_tracks.append({"id": "mv_qom", "label": "Motion-vector QoM (codec, P-frames)", "kind": "curve", "unit": "px", "hop_s": 1.0, "values": mv["magnitude"], "source": mv["source"], "mpeg7": "MotionActivity"})
        extra_tracks.append({"id": "mv_global", "label": "Global motion from vectors (camera)", "kind": "curve", "unit": "px", "hop_s": 1.0, "values": mv["global_motion"], "source": mv["source"]})
    data["research"] = research.research_block(data, out_dir)
    data["research"]["tracks"] += extra_tracks
    data["derivatives"] = metadata.derivatives(out_dir, data)
    log("9/9 export")
    export.write_json(data, out_dir / "segments.json")
    export.write_vtt(data, out_dir / "chapters.vtt")
    export.write_player(data, out_dir / "player.html", video_url or f"../{video.name}")
    try:
        musicops.timeline_png(segs, duration, out_dir / "timeline.png", ms_level, title=data["title"])
    except Exception as e:
        log(f"  timeline figure skipped: {e}")
    return data
