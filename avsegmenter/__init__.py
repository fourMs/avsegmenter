"""avsegmenter: split a concert video into pieces / applause / talk and describe each piece.

Built on three UiO toolboxes:
- musicalgestures (MGT-python): audio extraction, motion tracks (QoM, videograms), keyframes
- ambiscape: PANNs AudioSet tagging, 1 Hz level/spectral features, novelty segmentation
- musiscape: concert song finder, region classifier, per-piece music descriptors, timeline figure
"""
__version__ = "0.1.0"
from .config import Config  # noqa: F401
from .fusion import Segment  # noqa: F401
