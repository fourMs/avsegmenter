"""avsegmenter: segment audio-visual recordings of events (concerts, lectures, defences, panels) into
parts, pieces, speaker turns and segments; describe them; export players and standard metadata.

Built on three toolboxes from the fourMs lab:
- musicalgestures (MGT-python): audio extraction, motion tracks (QoM, videograms), keyframes
- ambiscape: PANNs AudioSet tagging, 1 Hz level/spectral features, novelty segmentation
- musiscape: concert song finder, region classifier, per-piece music descriptors, timeline figure
"""
__version__ = "0.1.0"
from .config import Config  # noqa: F401
from .fusion import Segment  # noqa: F401
