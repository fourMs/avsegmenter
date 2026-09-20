"""Running-order alignment: re-exported from ``musiscape.setlist``."""
from musiscape.setlist import load_setlist as load_programme, align_setlist as align, thanked_names, act_title  # noqa: F401

from musiscape.setlist import name_score  # noqa: E402,F401


def announced_at(cues: list[dict], act: dict, window_s: float = 45.0, min_score: float = 0.85) -> float | None:
    """When an act was announced, from the transcript, or ``None`` if nobody said its names.

    The projection is the surer witness to where an act begins, but a hall dims it for a
    performance, and then the only record is the host saying who is about to play. This slides a
    short window along the transcript and returns the end of the first window whose text names the
    act well enough: the act starts as the announcement finishes.
    """
    if not cues:
        return None
    best_t, best = None, min_score
    for k, c in enumerate(cues):
        text = " ".join((cues[j].get("text") or "") for j in range(k, len(cues))
                        if cues[j]["start"] < c["start"] + window_s)
        score, _ = name_score(text, act)
        if score > best:
            best, best_t = score, float(c["start"]) + window_s
    return best_t
