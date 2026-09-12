from __future__ import annotations
import argparse, os
from pathlib import Path
from .config import Config
from .pipeline import run


def main(argv=None) -> int:
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
    ap.add_argument("--skip", default="", help="comma list of stages to skip: video,speech,fingerprint")
    a = ap.parse_args(argv)
    cfg = Config(profile=a.profile, n_speakers=a.speakers, diarize=a.diarize, device=a.device, whisper_model=a.whisper_model,
                 motion_budget=float("inf") if a.motion_tracks else 3e11,
                 whisper_language=None if a.language == "auto" else a.language, acoustid_key=a.acoustid_key)
    video = Path(a.video)
    out = Path(a.out) if a.out else video.parent / "analysis"
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
