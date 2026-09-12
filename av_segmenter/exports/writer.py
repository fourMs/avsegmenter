"""Write every export for one analysis folder into ``<analysis>/export/`` (and optionally a bag)."""
from __future__ import annotations
import json
from pathlib import Path

from .record import build_record
from .ebucore import ebucore_xml
from .iiif import iiif_manifest, web_annotations
from .schemaorg import schemaorg_jsonld
from .provenance import premis_xml
from .validate import validate_all


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
    for name in ("chapters.vtt", "segments.json"):
        if (A / name).exists():
            (out / name).write_bytes((A / name).read_bytes())
    findings = validate_all(out)
    (out / "validation.json").write_text(json.dumps(findings, indent=1))
    for k, v in findings.items():
        log(f"  {k}: {'ok' if not v else '; '.join(v[:3])}")
    if bag:
        from .bag import make_bag
        files = {"export/" + p.name: p for p in out.iterdir() if p.is_file()}
        files.update({"player.html": A / "player.html", "thumbs": A / "thumbs", "videogram.png": A / "videogram.png"})
        info = {"Source-Organization": rec["descriptive"].get("organisation"), "External-Identifier": rec["identifier"],
                "External-Description": rec["descriptive"]["title"], "Internal-Sender-Description": "av-segmenter analysis and standard metadata exports",
                "video_sha256": rec["technical"].get("sha256")}
        vp = Path(rec["technical"]["path"])
        make_bag(A / "bag", files, info, video=vp if vp.exists() else None)
        log(f"  bag: {A / 'bag'}")
    return rec
