"""Title cards read off the projection: which readings count as a cue, and what they do to the parts."""
from avsegmenter.fusion import Segment
from avsegmenter.parts import find_parts
from avsegmenter.slides import title_cues


def _readings():
    return [
        {"start": 0.0, "end": 200.0, "text": "FLYTPUNKT 1 / Victoria Johnson / Anders Tveit"},
        {"start": 210.0, "end": 215.0, "text": "a build step nobody sees"},          # too short
        {"start": 300.0, "end": 600.0, "text": "DANCING EMBRYO / Diego Marin / Benedikte Wallace"},
        {"start": 610.0, "end": 700.0, "text": "DANCING EMBRYO / Diego Marin, / Benedikte Wallace"},  # same card, read again
        {"start": 900.0, "end": 960.0, "text": "Humans"},                            # too few words
    ]


def test_a_card_that_holds_is_a_cue_and_a_flicker_is_not():
    cues = title_cues(_readings())
    assert [c["t"] for c in cues] == [0.0, 300.0]
    assert cues[1]["end"] == 700.0            # the second reading of the same card extends it
    assert "DANCING EMBRYO" in cues[1]["text"]


def test_a_title_card_cuts_where_the_sound_gives_nothing():
    """Two acts running into each other with no applause and no silence between them."""
    segs = [Segment(0, 600, "speech"), Segment(600, 1200, "music"), Segment(1200, 1800, "speech")]
    without = [p for p in find_parts(segs, [], 1800.0) if p["kind"] == "part"]
    with_slides = [p for p in find_parts(segs, [], 1800.0,
                                         slide_cues=[{"t": 600.0, "text": "SECOND ACT / Someone"}])
                   if p["kind"] == "part"]
    assert len(without) == 1
    assert len(with_slides) == 2 and with_slides[1]["start"] == 600.0
    assert "slide" in with_slides[1]["cues"]


def test_a_short_act_with_a_title_card_survives_the_merging():
    """Two minutes of speech between two long parts: merged away on its own, kept when a card names it."""
    segs = [Segment(0, 600, "speech"), Segment(600, 720, "speech"), Segment(720, 1500, "speech")]
    plain = [p for p in find_parts(segs, [], 1500.0, slide_cues=[{"t": 600.0, "text": "A short address"}])
             if p["kind"] == "part"]
    assert len(plain) == 2                     # 120 s is below the floor, so it still merges
    kept = [p for p in find_parts(segs, [], 1500.0, split_floor_s= 60.0,
                                  slide_cues=[{"t": 600.0, "text": "A short address by someone"},
                                              {"t": 720.0, "text": "The next act entirely"}])
            if p["kind"] == "part"]
    assert len(kept) == 3, kept


def test_a_voice_inside_a_card_does_not_start_a_part():
    """A panellist who holds the floor is not a new act while the panel's card is still up."""
    segs = [Segment(0, 1800, "speech")]
    turns = [{"start": 0, "end": 600, "speaker": "S0"}, {"start": 600, "end": 1500, "speaker": "S1"},
             {"start": 1500, "end": 1800, "speaker": "S0"}]
    loud = [p for p in find_parts(segs, turns, 1800.0) if p["kind"] == "part"]
    quiet = [p for p in find_parts(segs, turns, 1800.0,
                                   slide_cues=[{"t": 0.0, "end": 1800.0, "text": "ONE LONG PANEL / with several people"}])
             if p["kind"] == "part"]
    assert len(loud) > 1                      # the new voice looks like a part without the card
    assert len(quiet) == 1, quiet             # with the card up, it is one act


def test_an_act_is_found_where_the_host_announces_it():
    """The projection goes dark for a performance, and the only record is the host saying who plays."""
    from avsegmenter.programme import announced_at
    cues = [{"start": 0, "end": 20, "text": "takk til panelet for en interessant diskusjon"},
            {"start": 20, "end": 40, "text": "vi skal nå høre og se Koka Nikoladse spille"},
            {"start": 40, "end": 60, "text": "vær så god"}]
    act = {"nr": "5", "act": "Video Percussion", "performers": "Koka Nikoladze, Norwegian Academy of Music"}
    t = announced_at(cues, act, window_s=20)
    assert t is not None and 20 <= t <= 60, t


def test_an_act_nobody_names_is_not_invented():
    from avsegmenter.programme import announced_at
    cues = [{"start": 0, "end": 20, "text": "og så går vi videre til neste post på programmet"}]
    act = {"nr": "5", "act": "Video Percussion", "performers": "Koka Nikoladze"}
    assert announced_at(cues, act, window_s=20) is None
