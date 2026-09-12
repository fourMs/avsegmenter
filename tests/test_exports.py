"""Standard exports from a small synthetic analysis folder: record, EBUCore, IIIF, schema.org, PREMIS, bag."""
import json
from pathlib import Path

import pytest
from lxml import etree

from av_segmenter.exports import build_record, write_all
from av_segmenter.exports.validate import validate_all, validate_bag


@pytest.fixture
def analysis(tmp_path):
    a = tmp_path / "analysis"; a.mkdir(); (a / "thumbs").mkdir()
    video = tmp_path / "concert.mp4"; video.write_bytes(b"\x00" * 1024)
    segs = {
        "title": "Test concert", "profile": "concert", "generated": "2026-09-12T20:00:00",
        "video": {"file": "concert.mp4", "duration": 300.0, "tech": {"file": "concert.mp4", "container": "QuickTime / MOV", "size_bytes": 1024,
                  "duration_s": 300.0, "width": 1280, "height": 720, "fps": 30.0, "pix_fmt": "yuv420p", "bit_depth": 8, "video_codec": "H.264",
                  "audio_codec": "AAC", "sample_rate_hz": 44100, "channels": 2, "created": "2026-08-24T10:00:00Z"}},
        "tools": {"musicalgestures": "1.32.0", "ambiscape": "0.50.0", "musiscape": "0.11.0"}, "config": {"win_s": 4},
        "segments": [{"id": "seg-000", "kind": "speech", "start": 0.0, "end": 60.0, "duration": 60.0, "confidence": 0.9, "title": "Talk", "transcript": "Welcome"},
                     {"id": "seg-001", "kind": "music", "start": 60.0, "end": 280.0, "duration": 220.0, "confidence": 0.8, "title": "3. Menuett – A. B.", "piece_index": 1},
                     {"id": "seg-002", "kind": "applause", "start": 280.0, "end": 300.0, "duration": 20.0, "confidence": 0.5, "title": "Applause"}],
        "pieces": [{"id": "seg-001", "index": 1, "start": 60.0, "end": 280.0, "duration": 220.0, "title": "3. Menuett – A. B.",
                    "plan": {"nr": "3", "act": "Piano", "work": "Menuett", "composer": "Agathe Backer Grøndahl", "performers": "A. B."},
                    "performers": {"estimate": 1}, "ensemble": "solo piano", "instruments": [{"label": "Piano", "p": 0.7}], "genres": [{"label": "Classical music", "p": 0.1}],
                    "music": {"tempo_bpm": 120.0}, "camera": {"shots": 1}, "rights": {"acoustid_match": []}}],
        "camera": {"cuts": [150.0], "summary": {"still": 0.9, "moving": 0.1, "cut": 0.0}, "n_shots": 2},
        "metadata": {"license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "rights_holder": "IMV",
                     "privacy": {"level": "yellow", "reasons": ["audience visible"]}, "copyrights": [{"nr": "3", "work": "Menuett", "composer": "Agathe Backer Grøndahl", "status": "public domain"}]},
        "tracks": {"level_db": [-30.0] * 300}, "videogram": None, "summary": {"music": 220, "speech": 60, "applause": 20, "silence": 0, "other": 0},
    }
    (a / "segments.json").write_text(json.dumps(segs))
    (a / "chapters.vtt").write_text("WEBVTT\n"); (a / "player.html").write_text("<p>player</p>")
    (a / "curated.json").write_text(json.dumps({"title": "Semesterstartkonsert H26", "venue": "Salen", "date": "2026-08-24", "language": "no",
                                                 "people": [{"name": "A. B.", "role": "performer"}], "access": "open"}))
    return a


def test_record_merges_curated_over_automatic(analysis):
    rec = build_record(analysis, base_url="https://dam.example/imv/1")
    assert rec["descriptive"]["title"] == "Semesterstartkonsert H26" and rec["descriptive"]["venue"] == "Salen"
    assert rec["rights"]["access"] == "open" and rec["rights"]["license"] == "CC BY 4.0"
    assert rec["structural"]["items"][0]["instruments"][0]["id"] in (None, "/m/05r5c")
    assert "title" in rec["provenance"]["curated_fields"]
    assert rec["technical"]["sha256"] and len(rec["technical"]["sha256"]) == 64


def test_all_exports_are_written_and_well_formed(analysis):
    write_all(analysis, base_url="https://dam.example/imv/1", bag=True, log=lambda *a: None)
    out = analysis / "export"
    for name in ("record.json", "ebucore.xml", "manifest.json", "annotations.json", "schemaorg.json", "premis.xml", "validation.json"):
        assert (out / name).exists(), name
    eb = etree.parse(str(out / "ebucore.xml")); ns = {"e": "urn:ebu:metadata-schema:ebucore", "dc": "http://purl.org/dc/elements/1.1/"}
    assert eb.xpath("string(//e:title/dc:title)", namespaces=ns) == "Semesterstartkonsert H26"
    parts = eb.xpath("//e:part", namespaces=ns)
    assert any(p.get("typeLabel") == "piece" for p in parts) and any(p.get("typeLabel") == "segment:applause" for p in parts)
    assert eb.xpath("string(//e:part[@typeLabel='piece']/e:partStartTime/e:normalPlayTime)", namespaces=ns) == "00:01:00.000"
    m = json.loads((out / "manifest.json").read_text())
    assert m["type"] == "Manifest" and m["items"][0]["duration"] == 300.0 and len(m["structures"]) == 1
    assert m["structures"][0]["items"][0]["id"].endswith("#t=60.0,280.0")
    so = json.loads((out / "schemaorg.json").read_text())
    assert so["@type"] == "VideoObject" and so["hasPart"][0]["startOffset"] == 60.0
    pr = etree.parse(str(out / "premis.xml"))
    assert len(pr.xpath("//p:event", namespaces={"p": "http://www.loc.gov/premis/v3"})) == 3
    findings = validate_all(out)
    assert all(not [f for f in v if "not well-formed" in f or "missing" in f] for v in findings.values()), findings
    assert validate_bag(analysis / "bag") == []
    assert (analysis / "bag" / "data" / "concert.mp4").exists()
