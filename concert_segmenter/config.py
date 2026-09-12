from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Config:
    profile: str = "concert"        # "concert" (pieces) | "talk" (speaker turns and parts: defences, seminars, panels)
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
    stage_filter: bool = True        # drop audience by position (raised stage, camera in the hall); off for slide captures / insets
    # speech
    whisper_model: str = "large-v3"
    whisper_language: str | None = "no"
    # fingerprint
    acoustid_key: str | None = None
    # talk profile
    speaker_threshold: float = 0.75   # cosine merge distance for speaker clustering (centred ECAPA embeddings)
    n_speakers: int | None = None     # fix the number of speakers instead of thresholding
    part_gap_s: float = 90.0          # a non-speech gap this long ends a part
    part_min_s: float = 240.0         # parts shorter than this are merged into a neighbour

    def for_profile(self) -> "Config":
        if self.profile == "talk":
            # music is rare and short in a defence (a sonification demo); talk should not fragment
            self.min_duration_s = {"music": 30.0, "speech": 4.0, "applause": 4.0, "silence": 20.0, "other": 8.0}
            self.weights = {"music": 0.8, "speech": 1.0, "applause": 1.6, "silence": 1.0}
            self.stage_filter = False     # lecture halls and slide captures with speaker insets: no raised stage to key on
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
