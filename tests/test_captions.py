"""Captions cut out of a whole-recording transcript for one part of it."""
import json

import pytest

from avsegmenter import captions


CUES = [{"start": 10.0, "end": 14.0, "text": "before the cut"},
        {"start": 98.0, "end": 103.0, "text": "straddling the head of the part"},
        {"start": 110.0, "end": 115.0, "text": "inside"},
        {"start": 198.0, "end": 204.0, "text": "straddling the tail"},
        {"start": 300.0, "end": 304.0, "text": "after the cut"}]
TURNS = [{"speaker": "S0", "start": 0.0, "end": 150.0}, {"speaker": "S1", "start": 150.0, "end": 400.0}]


def test_only_the_cues_of_the_span_survive_and_start_at_zero():
    c = captions.cues_for_span(CUES, 100.0, 200.0)
    assert [x["text"] for x in c] == ["straddling the head of the part", "inside", "straddling the tail"]
    assert c[0]["start"] == 0.0, "a cue that straddles the cut is clipped, not dropped"
    assert c[1]["start"] == pytest.approx(10.0)
    assert c[-1]["end"] == pytest.approx(100.0), "the tail is clipped to the end of the span"


def test_a_cue_takes_the_name_of_whoever_holds_most_of_it():
    c = captions.cues_for_span(CUES, 100.0, 300.0, TURNS, {"S0": "Anja Volk"})
    assert c[0]["speaker"] == "Anja Volk"
    assert c[-1]["speaker"] == "S1", "an unnamed cluster keeps its id"


def test_lines_wrap_at_two_lines_and_never_lose_words():
    long = " ".join(["multimodal"] * 12)
    w = captions.wrap(long)
    assert w.count("\n") == 1
    assert w.replace("\n", " ").split() == long.split()
    assert len(w.split("\n")[0]) <= captions.WIDTH


def test_the_file_is_webvtt_with_voice_spans(tmp_path):
    c = captions.cues_for_span(CUES, 100.0, 200.0, TURNS, {"S0": "Anja Volk"})
    t = captions.write_vtt(c, tmp_path / "p.vtt").read_text()
    assert t.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:03.000" in t
    assert "<v Anja Volk>" in t
    assert "<v " not in captions.write_vtt(c, tmp_path / "q.vtt", speakers="never").read_text()


def test_a_voice_is_named_where_it_takes_over_and_not_on_every_cue(tmp_path):
    """A subtitler marks a turn, not each line, and 400 repetitions of a name help nobody."""
    c = [{"start": 0, "end": 2, "text": "one", "speaker": "A"},
         {"start": 2, "end": 4, "text": "two", "speaker": "A"},
         {"start": 4, "end": 6, "text": "three", "speaker": "B"},
         {"start": 6, "end": 8, "text": "four", "speaker": "A"}]
    change = captions.write_vtt(c, tmp_path / "c.vtt").read_text()
    assert change.count("<v A>") == 2 and change.count("<v B>") == 1
    always = captions.write_vtt(c, tmp_path / "a.vtt", speakers="always").read_text()
    assert always.count("<v A>") == 3 and always.count("<v B>") == 1


def test_a_cue_is_never_shorter_than_the_floor(tmp_path):
    t = captions.write_vtt([{"start": 1.0, "end": 1.05, "text": "Yes."}], tmp_path / "p.vtt").read_text()
    assert "00:00:01.000 --> 00:00:01.500" in t


def test_for_spans_writes_one_file_per_span_and_counts_the_cues(tmp_path):
    (tmp_path / "whisper_full.json").write_text(json.dumps({"language": "en", "segments": CUES}))
    (tmp_path / "segments.json").write_text(json.dumps(
        {"speakers": {"turns": TURNS, "speakers": {"S0": {"name": "Anja Volk"}, "S1": {"name": None}}}}))
    n = captions.for_spans(tmp_path, {"1-part.mp4": {"start_s": 100, "end_s": 200},
                                      "2-part.mp4": {"start_s": 400, "end_s": 500}},
                           tmp_path / "out", log=lambda *a: None)
    assert n == {"1-part.vtt": 3, "2-part.vtt": 0}
    assert (tmp_path / "out" / "2-part.vtt").read_text().strip() == "WEBVTT"


def test_a_file_joined_from_two_spans_keeps_its_captions_in_step():
    # a stop taken out of the middle: the second span's cues start where the first span's picture ends
    c = captions.cues_for_spans(CUES, [(100.0, 120.0), (195.0, 210.0)])
    assert [x["text"] for x in c] == ["straddling the head of the part", "inside", "straddling the tail"]
    assert c[-1]["start"] == pytest.approx(20.0 + 3.0) and c[-1]["end"] == pytest.approx(20.0 + 9.0)


def test_for_spans_takes_joined_spans_from_the_index(tmp_path):
    (tmp_path / "whisper_full.json").write_text(json.dumps({"segments": CUES}))
    n = captions.for_spans(tmp_path, {"3-part.mp4": {"spans": [[100, 120], [195, 210]]}}, tmp_path / "trim", log=lambda *_: None)
    assert n == {"3-part.vtt": 3} and "00:00:23.000 --> 00:00:29.000" in (tmp_path / "trim" / "3-part.vtt").read_text()


def test_a_long_segment_is_broken_into_readable_cues():
    """A transcriber returns segments; a subtitle is at most two lines and a few seconds."""
    text = ("So that is why I think it does not matter if we have the same signal, or a different "
            "one, because the task is what decides which sources are worth combining at all.")
    out = captions.split_cue({"start": 100.0, "end": 125.0, "text": text, "speaker": "A"})
    assert len(out) > 1
    assert all(len(c["text"]) <= captions.MAX_CHARS for c in out)
    assert all(c["end"] - c["start"] <= captions.MAX_CUE_S + 0.01 for c in out)
    assert " ".join(c["text"] for c in out).split() == text.split(), "no word is lost"
    assert out[0]["start"] == 100.0 and out[-1]["end"] == pytest.approx(125.0)
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(out, out[1:])), "cues do not overlap"
    assert all(c["speaker"] == "A" for c in out)


def test_a_short_segment_is_left_alone():
    c = {"start": 1.0, "end": 3.0, "text": "Thank you for the conversation.", "speaker": "A"}
    assert captions.split_cue(c) == [c | {"start": 1.0, "end": 3.0}]


def test_a_piece_ends_at_a_full_stop_where_it_can():
    """Where the text must be split anyway, the break goes at the sentence end, not mid-clause."""
    text = ("This first sentence is long enough to pass the mark. And the second one then "
            "continues well past the budget for a single cue.")
    p = captions._pieces(text)
    assert p[0] == "This first sentence is long enough to pass the mark."
    assert " ".join(p).split() == text.split()


def test_text_that_fits_two_lines_is_left_whole():
    """84 characters is two lines, so it is a cue already and splitting it would only flicker."""
    text = "One short thing here. Then a second sentence of moderate length."
    assert captions._pieces(text) == [text]


def test_cues_never_overlap_even_when_the_transcript_does():
    """Two captions on screen at once is the defect; the earlier one ends where the next begins."""
    over = [{"start": 0.0, "end": 6.0, "text": "one", "speaker": "A"},
            {"start": 5.0, "end": 9.0, "text": "two", "speaker": "B"},
            {"start": 8.9, "end": 12.0, "text": "three", "speaker": "A"}]
    out = captions.deoverlap([dict(c) for c in over])
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(out, out[1:]))
    assert out[0]["end"] == 5.0 and out[1]["start"] == 5.0, "the later cue keeps its own onset"


def test_a_cue_does_not_sit_over_the_pause_after_it():
    """One word held for fifteen seconds is a caption that has outstayed its words."""
    out = captions.split_cue({"start": 0.0, "end": 16.0, "text": "anything.", "speaker": "A"})
    assert all(c["end"] - c["start"] <= captions.MAX_CUE_S + 1e-9 for c in out)


def test_the_span_of_a_real_transcript_comes_out_clean():
    """The invariants a player needs, over cues that overlap and run long, as whisper writes them."""
    raw = [{"start": 0.0, "end": 12.0, "text": "A " + "long sentence that carries on " * 6},
           {"start": 11.0, "end": 14.0, "text": "Overlapping reply."},
           {"start": 30.0, "end": 45.0, "text": "Two words"}]
    out = captions.cues_for_span(raw, 0.0, 60.0)
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(out, out[1:]))
    assert all(len(c["text"]) <= captions.MAX_CHARS for c in out)
    assert all(0 < c["end"] - c["start"] <= captions.MAX_CUE_S + 1e-9 for c in out)


def test_the_minimum_duration_never_pushes_a_cue_over_the_next(tmp_path):
    """The floor that makes a short cue readable must not undo the de-overlapping."""
    cues = [{"start": 0.0, "end": 0.1, "text": "that we"}, {"start": 0.12, "end": 3.0, "text": "call cognition."}]
    t = captions.write_vtt(cues, tmp_path / "p.vtt").read_text()
    stamps = [l for l in t.split("\n") if " --> " in l]
    assert stamps[0] == "00:00:00.000 --> 00:00:00.120"
    assert stamps[1].startswith("00:00:00.120")
