"""Build one demo folder from an analysis, and rewrite the index that lists them.

The demos drifted from the code because they were assembled by hand: they carried a player from
before the page title, the caption language and the crossorigin fix, and a report from before the
running-order fix. Everything a demo shows is generated here from the analysis it came from, so a
rebuild is the way to bring one up to date.

    python examples/build_demo.py DEMOROOT/slug --analysis DIR --video FILE --title T --subtitle S
    python examples/build_demo.py DEMOROOT/slug --analysis DIR --keep-video      # HTML only
    python examples/build_demo.py DEMOROOT --index                               # rewrite the index

The proxy is 720p with the audio treated as `avsegmenter.mastering` treats a part of its kind, since
a recording of a room is 20 LU too quiet to watch as it comes off the cards.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avsegmenter import export, mastering  # noqa: E402

COPY = ["segments.json", "captions.vtt", "chapters.vtt", "videogram.png", "colourgram.png",
        "motiongram.png", "timeline.png", "curated.json", "programme.json", "report.html"]
COPY_DIRS = ["thumbs", "export"]


def proxy(video: Path, out: Path, kind: str, height: int = 720, log=print) -> None:
    """A 720p copy with the audio levelled and brought to the target."""
    pre = mastering.prefilter(kind)
    target = mastering.Target()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn",
                        "-af", f"{pre},loudnorm=I={target.i}:TP={target.tp}:LRA={target.lra}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = mastering.parse_measurement(r.stderr)
    log(f"  audio measures {m['input_i']} LUFS after levelling, range {m['input_lra']} LU")
    af = (f"{pre},loudnorm=I={target.i}:TP={target.tp}:LRA={target.lra}:measured_I={m['input_i']}"
          f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
          f":offset={m['target_offset']}:linear=true")
    # The whole picture path stays on the card. `-hwaccel cuda` on its own copies every frame back to
    # system memory for a CPU `scale`, which measured 8.0 s against 6.8 s for `scale_cuda` on a 60 s
    # span, and is why the scaling rather than the encoder sets the pace of this pass.
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y",
                    "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(video),
                    "-vf", f"scale_cuda=-2:{height}", "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                    "-cq", "30", "-b:v", "2000k", "-maxrate", "4M", "-bufsize", "8M",
                    "-af", af, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
                   check=True)
    log(f"  {out.name} {out.stat().st_size / 1e9:.1f} GB")


def fix_audio(video: Path, out: Path, kind: str, log=print) -> None:
    """The same audio treatment with the picture copied, for a proxy that already exists."""
    pre, target = mastering.prefilter(kind), mastering.Target()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn",
                        "-af", f"{pre},loudnorm=I={target.i}:TP={target.tp}:LRA={target.lra}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = mastering.parse_measurement(r.stderr)
    log(f"  audio measures {m['input_i']} LUFS after levelling")
    af = (f"{pre},loudnorm=I={target.i}:TP={target.tp}:LRA={target.lra}:measured_I={m['input_i']}"
          f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
          f":offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(video), "-c:v", "copy",
                    "-max_muxing_queue_size", "4096", "-af", af, "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(out)], check=True)


def transcript_language(analysis: Path) -> str | None:
    """The language of an analysis made before the record carried the field, from its transcripts."""
    full = analysis / "whisper_full.json"
    if full.exists():
        return json.loads(full.read_text()).get("language")
    per = analysis / "transcripts.json"
    if per.exists():
        langs = {v.get("language") for v in json.loads(per.read_text()).values()
                 if isinstance(v, dict) and v.get("language")}
        if len(langs) == 1:
            return langs.pop()
    return None


def build(dest: Path, analysis: Path, video: Path | None, title: str, subtitle: str,
          keep_video: bool, kind: str, log=print) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    data = json.loads((analysis / "segments.json").read_text())
    name = f"{dest.name}.mp4"
    if not keep_video:
        if video is None:
            raise SystemExit("--video is required unless --keep-video is given")
        log(f"{dest.name}: proxy from {video.name}")
        proxy(video, dest / name, kind, log=log)
    elif not (dest / name).exists():
        raise SystemExit(f"--keep-video, but {dest / name} is not there")

    for f in COPY:
        if (analysis / f).exists():
            shutil.copy2(analysis / f, dest / f)
    for d in COPY_DIRS:
        if (analysis / d).exists():
            shutil.copytree(analysis / d, dest / d, dirs_exist_ok=True)

    if title:
        data["title"] = title
    if not data.get("language"):
        data["language"] = transcript_language(analysis)
        if data["language"]:
            log(f"  caption language {data['language']}, read from the transcript")
    export.write_json(data, dest / "segments.json")
    export.write_player(data, dest / "index.html", name)
    (dest / "README.txt").write_text(
        f"avsegmenter demo: {subtitle}\n\n"
        "Open index.html in a browser, or put this folder on any static web server.\n"
        "segments.json holds everything the player draws; export/ holds the standard metadata.\n"
        "Generated by examples/build_demo.py in github.com/fourMs/avsegmenter.\n")
    log(f"  {dest}/index.html")


CARD = ('<div class="card"><a href="{slug}/index.html">{title}</a><br>'
        '<small>{subtitle} · <a href="{slug}/report.html">report</a></small></div>')

INDEX = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>avsegmenter demos</title>
<style>body{{margin:0;font:17px/1.5 Helvetica,Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:40px 20px}}.w{{max-width:720px;margin:0 auto}}h1{{font-size:34px;font-weight:400;margin:0 0 6px}}p{{color:#475569;max-width:62ch}}a{{color:#0f172a;text-decoration:underline;text-underline-offset:.2em;text-decoration-thickness:.05em}}small{{color:#475569}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}}</style></head>
<body><div class="w"><h1>avsegmenter demos</h1><p>{lede}</p>
{cards}
<p>Code and documentation: <a href="https://github.com/fourMs/avsegmenter">github.com/fourMs/avsegmenter</a>.</p></div></body></html>
"""

LEDE = ("Recordings from the Department of Musicology, University of Oslo, segmented automatically "
        "into parts, pieces, speaker turns and segments. Click the strips to jump. Every value is an "
        "estimate except the programme and the curated fields; open the advanced view under each "
        "player to see how the analysis works.")


def write_index(root: Path, log=print) -> None:
    """One card per demo folder, ordered by the date in its cards.json."""
    cards = []
    for meta in sorted(root.glob("*/cards.json"), key=lambda p: json.loads(p.read_text())["date"]):
        c = json.loads(meta.read_text())
        cards.append(CARD.format(slug=meta.parent.name, title=c["title"], subtitle=c["subtitle"]))
    (root / "index.html").write_text(INDEX.format(lede=LEDE, cards="\n".join(cards)))
    log(f"{root}/index.html with {len(cards)} demo(s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest", help="the demo folder to build, or the demo root with --index")
    ap.add_argument("--analysis", default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--title", default="", help="the name the player's tab and heading carry")
    ap.add_argument("--subtitle", default="", help="the line under the card on the index")
    ap.add_argument("--date", default="", help="ISO date, which orders the cards")
    ap.add_argument("--kind", default="talk", choices=["talk", "music"], help="how the audio is treated")
    ap.add_argument("--keep-video", action="store_true", help="leave the proxy alone, rebuild the pages")
    ap.add_argument("--index", action="store_true", help="only rewrite the index of the demo root")
    a = ap.parse_args()
    dest = Path(a.dest)
    if a.index:
        write_index(dest)
        return 0
    if not a.analysis:
        ap.error("--analysis is required")
    build(dest, Path(a.analysis), Path(a.video) if a.video else None, a.title, a.subtitle,
          a.keep_video, a.kind)
    if a.date or a.title:
        (dest / "cards.json").write_text(json.dumps(
            {"title": a.title, "subtitle": a.subtitle, "date": a.date or "9999-12-31"}, indent=1, ensure_ascii=False))
    write_index(dest.parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
