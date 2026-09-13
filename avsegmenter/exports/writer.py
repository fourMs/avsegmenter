"""Write every export for one analysis folder into ``<analysis>/export/`` (and optionally a bag)."""
from __future__ import annotations
import json
from pathlib import Path

from .record import build_record


def research_name() -> str:
    from ..research import ADDITIONS
    return ADDITIONS
from .ebucore import ebucore_xml
from .iiif import iiif_manifest, web_annotations
from .schemaorg import schemaorg_jsonld
from .provenance import premis_xml
from .validate import validate_all
from .jams import jams_doc
from .mets import mets_xml


def write_all(analysis_dir: Path, video_path: Path | None = None, base_url: str | None = None, identifier: str | None = None,
              bag: bool = False, with_checksum: bool = True, log=print) -> dict:
    A = Path(analysis_dir); out = A / "export"; out.mkdir(exist_ok=True)
    rec = build_record(A, video_path, base_url, identifier, with_checksum=with_checksum)
    (out / "record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    (out / "ebucore.xml").write_bytes(ebucore_xml(rec))
    (out / "manifest.json").write_text(json.dumps(iiif_manifest(rec), ensure_ascii=False, indent=1))
    (out / "annotations.json").write_text(json.dumps(web_annotations(rec), ensure_ascii=False, indent=1))
    (out / "schemaorg.json").write_text(json.dumps(schemaorg_jsonld(rec), ensure_ascii=False, indent=1))
    (out / "premis.xml").write_bytes(premis_xml(rec))
    for name in ("chapters.vtt", "captions.vtt", "segments.json"):
        if (A / name).exists():
            (out / name).write_bytes((A / name).read_bytes())
    (out / "annotations.jams").write_text(json.dumps(jams_doc(rec), ensure_ascii=False, indent=1))
    tracks_dir = out / "tracks"; tracks_dir.mkdir(exist_ok=True)
    for t in (rec.get("research") or {}).get("tracks", []):
        if t.get("kind") != "curve":
            continue
        hop = t.get("hop_s", 1.0)
        (tracks_dir / f"{t['id']}.csv").write_text("time_s,value\n" + "".join(f"{i * hop:.3f},{'' if v is None else v}\n" for i, v in enumerate(t["values"])))
    # METS over the derivative files (paths as they will sit in a bag's data/)
    mets_files = []
    vp0 = Path(rec["technical"]["path"])
    if vp0.exists():
        mets_files.append({"id": "master", "path": vp0.name, "mimetype": "video/mp4", "size": rec["technical"].get("size_bytes"), "sha256": rec["technical"].get("sha256"), "use": "master"})
    for k, der in enumerate(rec.get("derivatives") or []):
        if der["path"].endswith("/"):
            continue
        mets_files.append({"id": f"d{k:02d}", "path": der["path"], "mimetype": der.get("mimetype"), "size": der.get("size_bytes"), "sha256": der.get("sha256"), "use": "derivative"})
    for k, p in enumerate(sorted(out.iterdir())):
        if p.is_file() and p.name != "mets.xml":
            mets_files.append({"id": f"x{k:02d}", "path": f"export/{p.name}", "mimetype": "application/xml" if p.suffix == ".xml" else "application/json" if p.suffix in (".json", ".jams") else "text/plain", "size": p.stat().st_size, "use": "metadata"})
    (out / "mets.xml").write_bytes(mets_xml(rec, mets_files))
    findings = validate_all(out)
    (out / "validation.json").write_text(json.dumps(findings, indent=1))
    for k, v in findings.items():
        log(f"  {k}: {'ok' if not v else '; '.join(v[:3])}")
    if bag:
        from .bag import make_bag
        files = {"export/" + p.name: p for p in out.iterdir() if p.is_file()}
        files.update({"player.html": A / "player.html", "thumbs": A / "thumbs", "videogram.png": A / "videogram.png", "captions.vtt": A / "captions.vtt",
                      "motiongram.png": A / "motiongram.png", "colourgram.png": A / "colourgram.png", "curated.json": A / "curated.json", "research_additions.json": A / research_name()})
        files["mets.xml"] = out / "mets.xml"
        info = {"Source-Organization": rec["descriptive"].get("organisation"), "External-Identifier": rec["identifier"],
                "External-Description": rec["descriptive"]["title"], "Internal-Sender-Description": "avsegmenter analysis and standard metadata exports",
                "video_sha256": rec["technical"].get("sha256")}
        vp = Path(rec["technical"]["path"])
        make_bag(A / "bag", files, info, video=vp if vp.exists() else None)
        log(f"  bag: {A / 'bag'}")
    return rec
