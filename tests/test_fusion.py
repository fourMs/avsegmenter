import numpy as np
from concert_segmenter.fusion import fuse, group_scores, Segment
from concert_segmenter.config import Config


def test_fuse_maps_musiscape_vocabulary_and_covers_the_recording():
    labels = ["Music", "Speech", "Applause", "Silence"]
    hop, win = 2.0, 4.0
    n = 60
    T = np.arange(n) * hop + win / 2
    P = np.zeros((n, 4), np.float32)
    P[:10, 1] = 0.9; P[10:45, 0] = 0.9; P[45:50, 2] = 0.6; P[50:, 1] = 0.9
    level = np.full(n, -25.0)
    segs = fuse(P, T, labels, level, n * hop, Config())
    assert [s.kind for s in segs] == ["speech", "music", "applause", "speech"]
    assert segs[0].start == 0.0 and segs[-1].end == n * hop
    assert all(isinstance(s, Segment) for s in segs) and segs[1].confidence > 0.8
    assert set(group_scores(P, labels)) == {"music", "speech", "applause", "silence"}
