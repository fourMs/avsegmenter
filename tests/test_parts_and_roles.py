"""Parts for any recording, speaker roles, and the automatic stage filter, on synthetic input."""
import numpy as np

from avsegmenter.fusion import Segment
from avsegmenter.parts import find_parts, title_parts
from avsegmenter.speakers import suggest_roles, speaker_of
from avsegmenter.performers import raised_stage


def _concert():
    # talk, piece, applause, talk, piece, applause, long silence (interval), talk, piece, applause
    return [Segment(0, 120, "speech"), Segment(120, 420, "music"), Segment(420, 430, "applause"), Segment(430, 470, "speech"),
            Segment(470, 900, "music"), Segment(900, 912, "applause"), Segment(912, 1200, "silence"),
            Segment(1200, 1230, "speech"), Segment(1230, 1600, "music"), Segment(1600, 1612, "applause")]


def test_concert_parts_split_only_at_the_interval():
    parts = find_parts(_concert(), [], 1612.0)
    kinds = [p["kind"] for p in parts]
    assert kinds == ["part", "break", "part"], parts
    assert parts[0]["end"] == 912.0 and parts[2]["start"] == 1200.0
    assert parts[0]["content_share"] > 0.9


def test_applause_followed_by_talk_starts_a_part():
    segs = [Segment(0, 60, "speech"), Segment(60, 900, "speech"), Segment(900, 912, "applause"), Segment(912, 1500, "speech")]
    parts = find_parts(segs, [], 1500.0)
    assert [p["kind"] for p in parts] == ["part", "part"] and parts[1]["start"] == 912.0
    assert "applause" in parts[1]["cues"]


def test_new_voice_that_holds_the_floor_starts_a_part():
    segs = [Segment(0, 1800, "speech")]
    turns = [{"speaker": "S0", "start": 0, "end": 600}, {"speaker": "S1", "start": 600, "end": 615},   # a question from the floor
             {"speaker": "S0", "start": 615, "end": 1000}, {"speaker": "S1", "start": 1000, "end": 1800}]
    parts = find_parts(segs, turns, 1800.0, min_s=120.0)
    assert len(parts) == 2 and parts[1]["start"] == 1000.0 and parts[1]["cues"] == ["speaker:S1"]


def test_title_parts_skips_the_chairs_opening_and_assigns_by_order():
    parts = [{"kind": "part", "index": 1, "start": 0, "end": 200, "duration": 200, "speakers": {"S9": 0.95}},
             {"kind": "part", "index": 2, "start": 200, "end": 2000, "duration": 1800, "speakers": {"S0": 0.8}},
             {"kind": "break", "start": 2000, "end": 2100, "duration": 100},
             {"kind": "part", "index": 3, "start": 2100, "end": 4000, "duration": 1900, "speakers": {"S1": 0.6}}]
    title_parts(parts, [{"nr": "1", "act": "Trial lecture"}, {"nr": "2", "act": "Opponent"}], roles={"S9": "host / chair"})
    assert [p["title"] for p in parts] == ["Chair", "Trial lecture", "Break", "Opponent"]


def test_roles_are_generic():
    stats = {"A": {"total_s": 3000, "first_at": 100}, "B": {"total_s": 400, "first_at": 0}, "C": {"total_s": 900, "first_at": 1500}, "D": {"total_s": 20, "first_at": 800}}
    r = suggest_roles(stats)
    assert r == {"A": "main speaker", "B": "host / chair", "C": "speaker 1", "D": "brief voice"}
    assert speaker_of([{"speaker": "A", "start": 0, "end": 60}, {"speaker": "B", "start": 60, "end": 80}], 0, 100) == {"A": 0.75, "B": 0.25}


def test_raised_stage_from_detections():
    stage = {"frames": [{"t": t, "boxes": [[0.3, 0.2, 0.45, 0.8, 0.9], [0.2, 0.8, 0.3, 1.0, 0.8]]} for t in range(20)]}
    hall = {"frames": [{"t": t, "boxes": [[0.1, 0.62, 0.25, 0.95, 0.9]]} for t in range(20)]}
    assert raised_stage(stage) is True and raised_stage(hall) is False and raised_stage({"frames": []}) is False
