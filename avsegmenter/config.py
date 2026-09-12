from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Config:
    profile: str = "concert"        # tuning defaults only: "concert" | "talk" (defences, seminars, panels). Every recording gets
                                    # the same hierarchy: parts -> pieces + speaker turns -> segments.
    # PANNs tagging
    win_s: float = 4.0
    hop_s: float = 2.0
    device: str = "auto"            # "auto" | "cuda" | "cpu"
    # frame decision
    silence_db: float = -60.0       # RMS dBFS below this = silence regardless of tags
    weights: dict = field(default_factory=lambda: {"music": 1.0, "speech": 1.0, "applause": 1.6, "silence": 1.0})
    other_floor: float = 0.25       # if best weighted score is below this -> "other"
    smooth_frames: int = 5          # mode filter width (frames)
    min_duration_s: dict = field(default_factory=lambda: {"music": 20.0, "speech": 6.0, "applause": 4.0, "silence": 10.0, "other": 6.0})
    snap_s: float = 6.0             # snap piece boundaries to musiscape song boundaries within this
    # video
    person_fps: float = 1.0
    person_conf: float = 0.40
    stage_filter: str | bool = "auto"  # "auto" reads the detections: raised stage -> on; heads low in the frame -> off
    # speech
    whisper_model: str = "large-v3"
    whisper_language: str | None = "no"
    # fingerprint
    acoustid_key: str | None = None
    # speakers and parts (all recordings)
    diarize: str = "auto"             # "auto": when there is at least diarize_min_speech_s of talk; "always" | "never"
    diarize_min_speech_s: float = 300.0
    speaker_threshold: float = 0.75   # cosine merge distance for speaker clustering (raw ECAPA embeddings)
    n_speakers: int | None = None     # fix the number of speakers instead of thresholding
    part_gap_s: float = 90.0          # a silence this long is a break between parts
    part_min_s: float = 240.0         # parts shorter than this are merged into a neighbour
    motion_budget: float = 3e11       # MGT motion tracks run when width*height*fps*duration is below this (about 90 min of 720p30)

    def for_profile(self) -> "Config":
        if self.profile == "talk":
            # a musical example in a lecture is still a piece, but talk must not fragment on short sounds
            self.min_duration_s = {"music": 30.0, "speech": 4.0, "applause": 4.0, "silence": 20.0, "other": 8.0}
            self.weights = {"music": 0.8, "speech": 1.0, "applause": 1.6, "silence": 1.0}
        return self


# AudioSet label groups used for the coarse classes
GROUPS: dict[str, list[str]] = {
    "music": ["Music", "Musical instrument", "Singing", "Choir", "A capella", "Piano", "Guitar",
              "Synthesizer", "Electronic music", "Drum kit", "Bass guitar", "Violin, fiddle"],
    "speech": ["Speech", "Male speech, man speaking", "Female speech, woman speaking",
               "Narration, monologue", "Conversation"],
    "applause": ["Applause", "Clapping", "Cheering", "Crowd"],
    "silence": ["Silence"],
}

INSTRUMENT_LABELS = [
    "Piano", "Electric piano", "Keyboard (musical)", "Organ", "Electronic organ", "Synthesizer",
    "Sampler", "Drum machine", "Guitar", "Electric guitar", "Bass guitar", "Acoustic guitar",
    "Steel guitar, slide guitar", "Banjo", "Mandolin", "Ukulele", "Harp", "Double bass",
    "Violin, fiddle", "Cello", "Bowed string instrument", "Plucked string instrument",
    "Drum kit", "Drum", "Snare drum", "Bass drum", "Cymbal", "Hi-hat", "Timpani", "Tabla",
    "Percussion", "Marimba, xylophone", "Vibraphone", "Glockenspiel", "Trumpet", "Trombone",
    "French horn", "Saxophone", "Clarinet", "Flute", "Oboe", "Bassoon", "Harmonica", "Accordion",
    "Brass instrument", "Wind instrument, woodwind instrument", "Singing", "Male singing",
    "Female singing", "Choir", "A capella", "Rapping", "Theremin", "Singing bowl", "Gong",
    "Effects unit", "Chorus effect", "Distortion", "Bell",
]

GENRE_LABELS = [
    "Pop music", "Hip hop music", "Rock music", "Heavy metal", "Punk rock", "Grunge",
    "Progressive rock", "Rock and roll", "Psychedelic rock", "Rhythm and blues", "Soul music",
    "Reggae", "Country", "Swing music", "Bluegrass", "Funk", "Folk music", "Middle Eastern music",
    "Jazz", "Disco", "Classical music", "Opera", "Electronic music", "House music", "Techno",
    "Dubstep", "Drum and bass", "Electronica", "Electronic dance music", "Ambient music",
    "Trance music", "Music of Latin America", "Salsa music", "Flamenco", "Blues",
    "Music for children", "New-age music", "Vocal music", "Music of Africa", "Afrobeat",
    "Christian music", "Gospel music", "Music of Asia", "Carnatic music", "Music of Bollywood",
    "Ska", "Traditional music", "Independent music", "Experimental music", "Noise music",
]
