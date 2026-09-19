"""Which treatment a part gets, and the commands that carry it out."""
import json

import pytest

from avsegmenter import mastering
from avsegmenter.mastering import Target


def _segments():
    return [{"start": 0, "end": 300, "kind": "speech"}, {"start": 300, "end": 340, "kind": "music"},
            {"start": 340, "end": 1200, "kind": "speech"}, {"start": 1200, "end": 2400, "kind": "music"}]


def test_a_lecture_with_a_demonstration_in_it_is_still_talk():
    """40 s of music inside 20 minutes of speech is a demonstration, not a reason to stop levelling."""
    part = {"start": 0, "end": 1200, "kind": "part", "index": 1}
    assert mastering.music_share(part, _segments()) == pytest.approx(40 / 1200)
    assert mastering.treatment(part, _segments()) == "talk"


def test_a_part_that_is_mostly_music_keeps_its_dynamics():
    part = {"start": 1200, "end": 2400, "kind": "part", "index": 2}
    assert mastering.music_share(part, _segments()) == pytest.approx(1.0)
    assert mastering.treatment(part, _segments()) == "music"


def test_talk_is_levelled_and_music_is_only_limited():
    talk, music = mastering.prefilter("talk"), mastering.prefilter("music")
    assert "dynaudnorm" in talk and "alimiter" in talk
    assert "dynaudnorm" not in music and "alimiter" in music


def test_the_limiter_ceiling_follows_the_true_peak_target():
    assert mastering.prefilter("music", Target(tp=-1.5)).endswith("limit=0.8414:level=false")
    assert "limit=1.0000" in mastering.prefilter("music", Target(tp=0.0))


def test_the_measuring_pass_asks_for_json_and_the_cut_asks_for_a_linear_gain():
    pre = mastering.prefilter("talk")
    m = mastering.measure_command("v.mp4", 10, 20, pre)
    assert "print_format=json" in " ".join(m) and "-vn" in m
    measured = {"input_i": "-30.0", "input_tp": "-8.0", "input_lra": "6.0",
                "input_thresh": "-40.0", "target_offset": "0.5"}
    c = mastering.cut_command("v.mp4", 10, 20, pre, measured, "out.mp4")
    af = c[c.index("-af") + 1]
    assert "linear=true" in af and "measured_I=-30.0" in af


def test_input_options_come_before_the_input():
    """-hwaccel, -ss and -to are input options; after -i ffmpeg stops with an error."""
    c = mastering.cut_command("v.mp4", 10, 20, mastering.prefilter("talk"), {
        "input_i": "-30", "input_tp": "-8", "input_lra": "6", "input_thresh": "-40", "target_offset": "0"},
        "out.mp4", hwaccel=True)
    i = c.index("-i")
    for opt in ("-hwaccel", "-ss", "-to"):
        assert c.index(opt) < i, f"{opt} must come before -i"


def test_cut_parts_names_and_indexes_every_part(tmp_path, monkeypatch):
    d = {"video": {"file": "v.mp4", "duration": 2400.0}, "segments": _segments(),
         "parts": [{"kind": "break", "start": 0, "end": 10},
                   {"kind": "part", "index": 1, "start": 0, "end": 1200, "title": "Trial lecture: on things"},
                   {"kind": "part", "index": 2, "start": 1200, "end": 2400, "title": "Recital"}]}
    (tmp_path / "segments.json").write_text(json.dumps(d))
    calls = []

    class R:
        stderr = '{"input_i":"-30.0","input_tp":"-8.0","input_lra":"6.0","input_thresh":"-40.0","target_offset":"0.5"}'

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "-f" in cmd and cmd[cmd.index("-f") + 1] == "null":
            return R()
        (tmp_path / "cut" / cmd[-1].split("/")[-1]).write_text("")
        return R()

    (tmp_path / "cut").mkdir()
    monkeypatch.setattr(mastering.subprocess, "run", fake_run)
    idx = mastering.cut_parts(tmp_path, tmp_path / "v.mp4", tmp_path / "cut", stem="laczko")
    assert list(idx) == ["1-laczko-trial-lecture-on-things.mp4", "2-laczko-recital.mp4"]
    assert idx["1-laczko-trial-lecture-on-things.mp4"]["treatment"] == "talk"
    assert idx["2-laczko-recital.mp4"]["treatment"] == "music"
    assert json.loads((tmp_path / "cut" / "parts.json").read_text()) == idx
