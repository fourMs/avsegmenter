"""A BagIt 1.0 bag (RFC 8493) of the record and its files, for deposit: data/, manifest-sha256.txt, bag-info.txt."""
from __future__ import annotations
import datetime as _dt
import hashlib
import shutil
from pathlib import Path


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def make_bag(bag_dir: Path, files: dict[str, Path], info: dict, video: Path | None = None, link_video: bool = True) -> Path:
    """``files`` maps bag-relative paths under data/ to sources. The video is hard-linked when possible
    (same filesystem) so a 36 GB file is not copied; set ``link_video=False`` to copy."""
    bag_dir = Path(bag_dir)
    if bag_dir.exists():
        shutil.rmtree(bag_dir)
    data = bag_dir / "data"; data.mkdir(parents=True)
    entries = {}
    for rel, src in files.items():
        src = Path(src)
        if not src.exists():
            continue
        dst = data / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
            for f in dst.rglob("*"):
                if f.is_file():
                    entries[str(f.relative_to(bag_dir))] = _sha256(f)
        else:
            shutil.copy2(src, dst); entries[str(dst.relative_to(bag_dir))] = _sha256(dst)
    if video and Path(video).exists():
        dst = data / Path(video).name
        try:
            if link_video:
                import os; os.link(video, dst)
            else:
                shutil.copy2(video, dst)
        except OSError:
            shutil.copy2(video, dst)
        entries[str(dst.relative_to(bag_dir))] = info.get("video_sha256") or _sha256(dst)
    (bag_dir / "bagit.txt").write_text("BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n")
    (bag_dir / "manifest-sha256.txt").write_text("".join(f"{h}  {p}\n" for p, h in sorted(entries.items())))
    total = sum((bag_dir / p).stat().st_size for p in entries)
    lines = {"Bagging-Date": _dt.date.today().isoformat(), "Payload-Oxum": f"{total}.{len(entries)}", "Bag-Software-Agent": "avsegmenter exports.bag", **{k: v for k, v in info.items() if v and k != "video_sha256"}}
    (bag_dir / "bag-info.txt").write_text("".join(f"{k}: {v}\n" for k, v in lines.items()))
    tagm = {n: _sha256(bag_dir / n) for n in ("bagit.txt", "bag-info.txt", "manifest-sha256.txt")}
    (bag_dir / "tagmanifest-sha256.txt").write_text("".join(f"{h}  {n}\n" for n, h in tagm.items()))
    return bag_dir
