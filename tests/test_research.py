"""Research layer: importers, additions, and the block the player reads."""
import json
from pathlib import Path

from avsegmenter import research


def test_read_elan_tab_export_and_plain_csv(tmp_path):
    eaf_csv = tmp_path / "notes.txt"
    eaf_csv.write_text("Tier\tBegin Time - ss.msec\tEnd Time - ss.msec\tDuration - ss.msec\tAnnotation\nGesture\t12.5\t14.0\t1.5\tbow lift\nGesture\t20.0\t21.0\t1.0\tnod\nHarmony\t30\t30\t0\tV-I\n")
    tiers = research.read_elan_csv(eaf_csv)
    assert [t["id"] for t in tiers] == ["gesture", "harmony"]
    assert tiers[0]["items"][0] == {"start": 12.5, "end": 14.0, "label": "bow lift"} and tiers[1]["kind"] == "point"
    plain = tmp_path / "plain.csv"; plain.write_text("start,end,label\n0:01:00,0:01:05,entry\n90,95,exit\n")
    t = research.read_elan_csv(plain)
    assert t[0]["items"] == [{"start": 60.0, "end": 65.0, "label": "entry"}, {"start": 90.0, "end": 95.0, "label": "exit"}]


def test_read_eaf(tmp_path):
    eaf = tmp_path / "a.eaf"
    eaf.write_text('''<?xml version="1.0"?><ANNOTATION_DOCUMENT><TIME_ORDER><TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1000"/><TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="2500"/></TIME_ORDER>
<TIER TIER_ID="Pose events"><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1" TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts2"><ANNOTATION_VALUE>arm raise</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION></TIER></ANNOTATION_DOCUMENT>''')
    tiers = research.read_eaf(eaf)
    assert tiers[0]["id"] == "pose_events" and tiers[0]["items"] == [{"start": 1.0, "end": 2.5, "label": "arm raise"}]


def test_additions_survive_and_merge(tmp_path):
    out = tmp_path; (out / "x.csv").write_text("time,value\n0,0\n2,1\n4,0\n")
    research.add_track(out, out / "x.csv", "hand_qom", label="Hand QoM", unit="a.u.", hop_s=1.0, author="me")
    (out / "t.csv").write_text("start,end,label\n1,2,a\n")
    research.add_tier(out, out / "t.csv", tier_id="marks", label="Marks")
    d = {"video": {"duration": 10.0}, "segments": [{"start": 0, "end": 10, "kind": "music", "confidence": 0.9}], "tracks": {"hop_s": 1.0, "level_db": [-20.0] * 10}}
    R = research.research_block(d, out)
    ids = [t["id"] for t in R["tracks"]]
    assert "level_db" in ids and "hand_qom" in ids
    hq = next(t for t in R["tracks"] if t["id"] == "hand_qom"); assert hq["values"][:5] == [0.0, 0.5, 1.0, 0.5, 0.0] and hq["author"] == "me"
    assert [t["id"] for t in R["tiers"]] == ["segments", "marks"]
    add = json.loads((out / research.ADDITIONS).read_text()); assert len(add["tracks"]) == 1 and len(add["tiers"]) == 1
