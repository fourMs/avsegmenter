from __future__ import annotations
import argparse, os
from pathlib import Path
from .config import Config
from .pipeline import run


def _subcommand(argv) -> int | None:
    """``avsegmenter add-tier|add-track|refresh|cut OUT ...``: work on an analysis folder without
    re-running it."""
    import json, sys
    from pathlib import Path
    from . import research, export
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("add-tier", "add-track", "refresh", "cut", "captions"):
        return None
    if args[0] == "cut":
        return _cut(args[1:])
    if args[0] == "captions":
        return _captions(args[1:])
    sp = argparse.ArgumentParser(prog=f"avsegmenter {args[0]}")
    sp.add_argument("out", help="the analysis folder")
    if args[0] in ("add-tier", "add-track"):
        sp.add_argument("file", help="ELAN .eaf / ELAN tab export / CSV (add-tier) or CSV time,value (add-track)")
        sp.add_argument("--id", default=None); sp.add_argument("--label", default=None); sp.add_argument("--author", default=None)
    if args[0] == "add-track":
        sp.add_argument("--unit", default=None); sp.add_argument("--hop", type=float, default=1.0)
    a = sp.parse_args(args[1:])
    out = Path(a.out)
    if args[0] == "add-tier":
        ids = research.add_tier(out, Path(a.file), a.id, a.label, a.author); print("added tiers:", ", ".join(ids))
    elif args[0] == "add-track":
        if not a.id:
            sp.error("--id is required for add-track")
        print("added track:", research.add_track(out, Path(a.file), a.id, a.label, a.unit, a.hop, a.author))
    data = json.loads((out / "segments.json").read_text())
    data["research"] = research.research_block(data, out)
    export.write_json(data, out / "segments.json")
    export.write_player(data, out / "player.html", data["video"].get("url") or data["video"]["file"])
    from .exports import write_all
    write_all(out, None, base_url=data.get("base_url"), with_checksum=False, log=lambda *x: None)
    print(f"refreshed {out}/segments.json, player.html and export/")
    return 0


def _captions(args) -> int:
    """``avsegmenter captions OUT ...``: a .vtt for each file cut out of the recording.

    The transcript is timed against the whole recording, so a part needs its cues shifted."""
    import json
    from . import captions as cap
    sp = argparse.ArgumentParser(prog="avsegmenter captions")
    sp.add_argument("out", help="the analysis folder")
    sp.add_argument("--index", default=None, help="JSON mapping each file to its start_s and end_s, such as trim/parts.json")
    sp.add_argument("--span", action="append", default=[], metavar="NAME=START:END",
                    help="one span in seconds, repeatable, for files cut outside avsegmenter")
    sp.add_argument("--part", action="append", type=int, default=[], help="a detected part, by index")
    sp.add_argument("--dir", default=None, help="where the .vtt files go (default: beside the index, else <out>/../trim)")
    sp.add_argument("--speakers", default="change", choices=["change", "always", "never"],
                    help="name a voice where it takes over (default), on every cue, or not at all")
    a = sp.parse_args(args)
    out = Path(a.out)
    spans, dest = {}, Path(a.dir) if a.dir else None
    if a.index:
        idx = json.loads(Path(a.index).read_text())
        for name, v in idx.items():
            if isinstance(v, dict) and "start_s" in v:
                spans[name] = v
            elif isinstance(v, dict) and "offset_s" in v:      # a trims_alignment.json
                spans[name] = {"start_s": v["offset_s"], "end_s": v["offset_s"] + v["duration_s"]}
        dest = dest or Path(a.index).parent
    for spec in a.span:
        name, _, times = spec.partition("=")
        start, _, end = times.partition(":")
        spans[name] = {"start_s": float(start), "end_s": float(end)}
    if a.part:
        data = json.loads((out / "segments.json").read_text())
        for p in (data.get("parts") or []):
            if p.get("kind") == "part" and p.get("index") in a.part:
                spans[f"part-{p['index']}"] = {"start_s": p["start"], "end_s": p["end"]}
    if not spans:
        sp.error("nothing to do: give --index, --span or --part")
    n = cap.for_spans(out, spans, dest or out.parent / "trim", speakers=a.speakers)
    print(f"{len(n)} caption file(s), {sum(n.values())} cues")
    return 0


def _cut(args) -> int:
    """``avsegmenter cut OUT --video V``: one file per part, each levelled and brought to a target.

    Speech and music are treated differently, since a leveller that helps a panel ruins a crescendo;
    see ``avsegmenter.mastering``."""
    import json
    from . import mastering
    sp = argparse.ArgumentParser(prog="avsegmenter cut")
    sp.add_argument("out", help="the analysis folder")
    sp.add_argument("--video", default=None, help="the recording (default: the one the analysis names)")
    sp.add_argument("--dir", default=None, help="where the files go (default: <out>/../trim)")
    sp.add_argument("--target", type=float, default=-16.0, help="integrated loudness in LUFS (broadcast delivery: -23)")
    sp.add_argument("--true-peak", type=float, default=-1.5, help="ceiling in dBTP")
    sp.add_argument("--pad", type=float, default=0.0, help="seconds of air at each end of a part")
    sp.add_argument("--stem", default="", help="name to put in every filename, such as a surname")
    sp.add_argument("--no-hwaccel", action="store_true", help="decode on the CPU")
    sp.add_argument("--plain", action="store_true", help="no levelling anywhere, only the loudness gain")
    sp.add_argument("--no-captions", action="store_true", help="do not write a .vtt beside each file")
    a = sp.parse_args(args)
    out = Path(a.out)
    data = json.loads((out / "segments.json").read_text())
    video = Path(a.video) if a.video else (out.parent / data["video"]["file"])
    if not video.exists():
        sp.error(f"cannot find the recording at {video}; pass --video")
    if a.plain:
        mastering.LEVELLER = ""
    target = mastering.Target(i=a.target, tp=a.true_peak)
    dest = Path(a.dir) if a.dir else out.parent / "trim"
    idx = mastering.cut_parts(out, video, dest, target=target, pad_s=a.pad, stem=a.stem,
                              hwaccel=not a.no_hwaccel)
    if not a.no_captions:
        from . import captions as cap
        cap.for_spans(out, idx, dest)
    print(f"{len(idx)} part(s) in {dest}")
    return 0


def main(argv=None) -> int:
    rc = _subcommand(argv)
    if rc is not None:
        return rc
    ap = argparse.ArgumentParser(prog="avsegmenter", description="Segment a concert video into pieces / applause / talk.")
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None, help="output directory (default: <video dir>/analysis)")
    ap.add_argument("--video-url", default=None, help="URL the web player should load the video from")
    ap.add_argument("--title", default=None)
    ap.add_argument("--profile", default="concert", choices=["concert", "talk"], help="concert: pieces; talk: speaker turns and parts (defence, seminar, panel)")
    ap.add_argument("--speakers", type=int, default=None, help="fix the number of speakers (default: clustering decides)")
    ap.add_argument("--diarize", default="auto", choices=["auto", "always", "never"], help="speaker turns: auto = when there is 5+ min of talk")
    ap.add_argument("--motion-tracks", action="store_true", help="force MGT motion tracks even for long high-resolution files")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--whisper-python", default=None, help="interpreter that has faster-whisper installed")
    ap.add_argument("--whisper-model", default="large-v3")
    ap.add_argument("--language", default="no", help="spoken language code, or 'auto'")
    ap.add_argument("--acoustid-key", default=os.environ.get("ACOUSTID_API_KEY"))
    ap.add_argument("--programme", default=None, help="running order (.docx kjøreplan table or .json) to align pieces to")
    ap.add_argument("--metadata", default=None, help="JSON with license, privacy level (green|yellow|red) and known copyrights")
    ap.add_argument("--base-url", default=None, help="public URL of the folder the DAM serves the recording and exports from (IIIF ids)")
    ap.add_argument("--identifier", default=None, help="persistent identifier of the recording (URN/DOI/handle)")
    ap.add_argument("--bag", action="store_true", help="also write a BagIt bag for deposit")
    ap.add_argument("--no-checksum", action="store_true", help="skip SHA-256 of the video (slow on very large files)")
    ap.add_argument("--slides", action="store_true",
                    help="read the projected slides first (needs easyocr) and use the title cards as part boundaries and act names")
    ap.add_argument("--slide-crop", default=None, help="ffmpeg crop for the projection area (default: the middle of the upper half)")
    ap.add_argument("--skip", default="", help="comma list of stages to skip: video,speech,fingerprint,speakers,quality,features,export")
    a = ap.parse_args(argv)
    cfg = Config(profile=a.profile, n_speakers=a.speakers, diarize=a.diarize, device=a.device, whisper_model=a.whisper_model,
                 motion_budget=float("inf") if a.motion_tracks else 3e11,
                 whisper_language=None if a.language == "auto" else a.language, acoustid_key=a.acoustid_key)
    video = Path(a.video)
    out = Path(a.out) if a.out else video.parent / "analysis"
    if a.slides:
        from . import slides as slidesmod
        out.mkdir(parents=True, exist_ok=True)
        try:
            slidesmod.detect_slides(video, out, crop=a.slide_crop or slidesmod.CROP)
        except ImportError as exc:
            print(f"slides: {exc}")
    data = run(video, out, cfg, video_url=a.video_url, title=a.title, whisper_python=a.whisper_python,
               skip=set(filter(None, a.skip.split(","))), programme_path=a.programme, metadata_path=a.metadata)
    print(f"\n{len(data['pieces'])} pieces, {len(data['segments'])} segments -> {out}/player.html")
    if "export" not in set(filter(None, a.skip.split(","))):
        from .exports import write_all
        print("exports:")
        write_all(out, video, base_url=a.video_url.rsplit("/", 1)[0] if (a.video_url and not a.base_url) else a.base_url,
                  identifier=a.identifier, bag=a.bag, with_checksum=not a.no_checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
