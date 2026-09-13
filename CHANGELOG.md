# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0], 2026-09-13

First release, developed on two recordings of the Department of Musicology, University of Oslo: a
semester-start concert (87 min, nine acts, moving camera) and a PhD defence (3 h 24 min, 1080p50).

### Added
- Segmentation of any recording into music / talk / applause / silence / other from AudioSet
  posteriors (PANNs through `ambiscape.ml.tag_frames`, chain in `musiscape.tagging`), with piece
  onsets refined to the first sound.
- One hierarchy for every recording: parts (breaks, applause followed by talk, arrival of a voice
  that holds the floor) → pieces (music) and speaker turns (silero VAD + ECAPA + clustering,
  whenever there are five minutes of talk) → segments.
- Per-piece description: instruments and genre tags (AudioSet), singing, key / tempo / pulse clarity /
  dynamics (musiscape), internal song-change cues, Chromaprint fingerprints with optional AcoustID lookup.
- People on stage per still camera framing (`musicalgestures.detect_people`, `camera_motion`,
  `performer_count`): widest framing for a piece, typical framing for a talk part; audience filter
  switched on when the detections show a raised stage.
- Camera cuts and pan/tilt/zoom; MGT motion tracks and videogram when the file is within budget.
- Transcripts (faster-whisper, per segment or one whole-file pass) attached to segments and turns.
- Running-order alignment (`musiscape.setlist`): a `.docx` table or a JSON list of acts, matched on the
  names in the spoken introductions (concerts) or by order (talks); unmatched acts reported.
- Web layer: `player.html` (video, camera cuts, videogram, waveform coloured by segment, part bands
  and numbered pieces, speaker row, detail panel, light/dark, metadata box) and a drop-in
  `segments-player.js` for any HTML5 video element; `chapters.vtt`.
- Standard metadata exports from a canonical record: EBUCore 1.10 (validated against the EBU XSD),
  IIIF Presentation 3 with nested ranges and annotation pages, W3C Web Annotation, schema.org JSON-LD,
  PREMIS 3 provenance, BagIt 1.0 bags for deposit; a curated overlay (`curated.json`) that a re-run
  never overwrites.
- Report generator (`avsegmenter.report`) for a shareable HTML summary.
- Quality and deposit: EBU R128 loudness, QC items (EBU Tech 3363 subset) as a PREMIS event, captions
  (WebVTT), derivatives manifest, JAMS export of the tiers, and a METS envelope with a timed structural
  map; standard audio descriptors with MPEG-7 names, picture brightness/saturation and a colourgram,
  motion-vector QoM from the codec, all as research tracks.
- Research layer: generic `research.tracks` (curve / state / image) and `research.tiers` (interval /
  point) in the record, an "Advanced view" in the player that draws them as lanes with deep links and
  CSV export, `avsegmenter add-track` / `add-tier` (ELAN .eaf, ELAN tab export, CSV) stored in
  `research_additions.json`, tiers exported as IIIF annotation pages and curves as CSV datasets.
