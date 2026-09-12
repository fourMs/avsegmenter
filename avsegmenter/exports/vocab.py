"""Controlled vocabularies: identifiers instead of free strings, so records from different concerts
and different tools can be compared and deposited."""
from __future__ import annotations
import csv
from functools import lru_cache
from pathlib import Path

AUDIOSET_ONTOLOGY = "https://research.google.com/audioset/ontology/"
EBU_ROLE_CS = "http://www.ebu.ch/metadata/cs/ebu_RoleCodeCS.xml"
EBU_GENRE_CS = "http://www.ebu.ch/metadata/cs/ebu_ContentGenreCS.xml"
MPEG7_CAMERA = "urn:mpeg:mpeg7:cs:CameraMotionCS:2001"

#: Our segment classes -> AudioSet labels that define them (the first is the representative one)
SEGMENT_CLASS_LABELS = {
    "music": ["Music"], "speech": ["Speech"], "applause": ["Applause"], "silence": ["Silence"], "other": ["Sound effect"],
}
#: Stable identifiers for the classes themselves live under the record's URN prefix
DEFAULT_URN_PREFIX = "urn:avsegmenter"


def segment_class_id(kind: str, prefix: str = DEFAULT_URN_PREFIX) -> str:
    return f"{prefix}:segment-class:{kind}"


def part_kind_id(kind: str, prefix: str = DEFAULT_URN_PREFIX) -> str:
    return f"{prefix}:part-kind:{kind}"

#: MPEG-7 CameraMotionCS terms for the camera states we produce
CAMERA_STATE_TERMS = {"still": "fixed", "moving": "pan-tilt-zoom", "cut": "cut"}

#: EBU RoleCodeCS labels used for people (term identifiers differ between CS versions; the label
#: is what EBUCore records in ``typeLabel`` and the CS in ``typeDefinition``)
ROLE_LABELS = {
    "performer": "Performer", "composer": "Composer", "lyricist": "Lyricist", "conductor": "Conductor",
    "presenter": "Presenter", "lecturer": "Lecturer", "candidate": "Candidate", "opponent": "Opponent",
    "chair": "Chair", "committee": "Committee member", "supervisor": "Supervisor", "organiser": "Organiser",
    "camera": "Camera operator", "producer": "Producer", "rights_holder": "Rights holder",
}
#: EBU ContentGenreCS labels for our two profiles
PROFILE_GENRE = {"concert": "Concert", "talk": "Lecture"}


@lru_cache(maxsize=1)
def audioset_ids() -> dict[str, str]:
    """AudioSet display name -> machine id (``/m/…``), from the PANNs class list if it is installed."""
    for cand in (Path.home() / "panns_data" / "class_labels_indices.csv",):
        if cand.exists():
            with open(cand, newline="") as fh:
                return {row["display_name"]: row["mid"] for row in csv.DictReader(fh)}
    return {}


def audioset_term(label: str) -> dict:
    mid = audioset_ids().get(label)
    return {"label": label, "id": mid, "uri": f"{AUDIOSET_ONTOLOGY}#{mid.replace('/', '_')}" if mid else None,
            "scheme": AUDIOSET_ONTOLOGY}


def role_term(role: str) -> dict:
    key = role.lower().split()[0] if role else ""
    return {"label": ROLE_LABELS.get(key, role.title() if role else "Contributor"), "scheme": EBU_ROLE_CS}
