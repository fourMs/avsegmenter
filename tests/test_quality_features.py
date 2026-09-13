"""Loudness/QC parsing, captions, JAMS and METS shapes, on small synthetic input."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from lxml import etree

from avsegmenter import quality, features
from avsegmenter.exports.jams import jams_doc
from avsegmenter.exports.mets import mets_xml


@pytest.fixture
def tone(tmp_path):
    sr = 48000; t = np.arange(sr * 8) / sr
    y = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32); y[: sr * 2] = 0   # 2 s of silence, then a tone
    p = tmp_path / "a.wav"; sf.write(str(p), np.stack([y, y], 1), sr); return p


def test_loudness_r128(tone, tmp_path):
    lo = quality.loudness(tone, tmp_path)
    assert lo["integrated_lufs"] is not None and -40 < lo["integrated_lufs"] < -10
    assert lo["true_peak_dbtp"] is not None and lo["loudness_range_lu"] is not None
    assert len(lo["momentary_lufs_1hz"]) >= 6 and lo["momentary_lufs_1hz"][0] is None and lo["momentary_lufs_1hz"][-1] is not None


def test_qc_items(tone, tmp_path):
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:r=10:d=3", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=5",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-pix_fmt", "yuv420p", str(v)], check=True, capture_output=True)
    q = quality.qc(v, tone, tmp_path)
    ids = {i["id"]: i for i in q["items"]}
    assert ids["black_frames"]["count"] >= 1 and ids["black_frames"]["outcome"] == "pass"     # black only at the head
    assert ids["silence"]["count"] >= 0 and ids["clipping"]["outcome"] == "pass" and "frame_integrity" in ids


def test_captions_vtt(tmp_path):
    p = features.captions_vtt([{"start": 1.0, "end": 2.5, "text": "Velkommen."}, {"start": 3.0, "end": 3.2, "text": "Ja."}], tmp_path / "c.vtt")
    s = p.read_text()
    assert s.startswith("WEBVTT") and "00:00:01.000 --> 00:00:02.500" in s and "00:00:03.000 --> 00:00:03.500" in s


def _rec():
    return {"identifier": "urn:x:1", "schema": "urn:avsegmenter:record:1.0",
            "descriptive": {"title": "T", "people": [{"name": "A", "role": "performer"}], "organisation": "Org"},
            "technical": {"duration_s": 100.0, "path": "/nonexistent.mp4", "size_bytes": 1},
            "structural": {"items": [{"kind": "part", "index": 1, "title": "P1", "start": 0, "end": 100}, {"kind": "piece", "index": 1, "title": "Piece", "start": 10, "end": 50, "part_index": 1}]},
            "rights": {"license": "CC", "access": "open", "privacy": {"level": "green"}},
            "provenance": {"software": [{"name": "avsegmenter", "version": "0.1.0"}], "generated": "2026-09-13T00:00:00", "record_built": "2026-09-13T00:00:00"},
            "research": {"tracks": [], "tiers": [{"id": "pieces", "label": "Pieces", "kind": "interval", "items": [{"start": 10, "end": 50, "label": "Piece"}]},
                                                 {"id": "cuts", "label": "Cuts", "kind": "point", "items": [{"start": 20, "end": 20, "label": "cut"}]}]},
            "quality": {"loudness": {"integrated_lufs": -23.0, "loudness_range_lu": 8.0, "true_peak_dbtp": -1.5}, "qc": {"standard": "x", "items": [{"id": "black_frames", "outcome": "pass", "count": 0, "label": "Black"}]}}}


def test_jams_and_mets_shapes():
    rec = _rec()
    j = jams_doc(rec)
    assert j["file_metadata"]["duration"] == 100.0 and [a["namespace"] for a in j["annotations"]] == ["segment_open", "tag_open"]
    assert j["annotations"][0]["data"][0] == {"time": 10.0, "duration": 40.0, "value": "Piece", "confidence": None}
    x = mets_xml(rec, [{"id": "master", "path": "v.mp4", "mimetype": "video/mp4", "size": 1, "sha256": "ab", "use": "master"}])
    doc = etree.fromstring(x); ns = {"m": "http://www.loc.gov/METS/"}
    assert doc.xpath("count(//m:fileGrp)", namespaces=ns) == 1
    divs = doc.xpath("//m:structMap//m:div[@TYPE='piece']", namespaces=ns)
    assert len(divs) == 1 and divs[0].xpath("m:fptr/m:area/@BEGIN", namespaces=ns) == ["00:00:10.000"]
    assert doc.xpath("string(//m:techMD[@ID='tech-quality']//loudness/integrated_lufs)", namespaces=ns) == "-23.0"
