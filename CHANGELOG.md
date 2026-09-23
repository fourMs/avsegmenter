# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `avsegmenter.slides` and `avsegmenter --slides`: read the projected slides and use the title cards
  as part boundaries and act names. A hall that runs from a running order puts up a card when an act
  begins, with the work and the people in it. It is written rather than spoken, so it survives a
  bilingual event and a host who says nothing, and it changes exactly when the act changes. Readings
  of one card are merged on the words they share; a card counts when it holds for twenty seconds or
  carries eight words, so a card the hall dims for a performance still counts; a slide that comes back
  later in the evening is the house slide, not a title, and is ranked down; and where the running
  order says how many acts there were, that many of the most title-like cards are kept. While a card
  is up the act is running, so a change of voice inside its span no longer cuts. A part takes its
  name from the card held in the middle of it, not from either end, where the previous act's card
  may still be up or the next one's already showing. Optical character recognition is an optional
  dependency (`pip install easyocr`); without it nothing changes.

- An act that the projection missed is recovered from what was said. Where the running order has an
  act that no part carries, `programme.announced_at` slides a window along the transcript and returns
  the moment the host named it; the part it falls inside is cut there, and the alignment runs again.
  A hall dims the screen for a performance, and then the spoken announcement is the only record of
  where the act began. On the opening of a research centre this recovered the percussion piece that
  closed the evening, the one act the cards had lost, and no act was left unnamed.
- Parts follow the running order where one is given. `find_parts(..., expect_parts=n)` splits its
  longest parts again at the applause inside them, strongest burst first, until it has as many parts
  as the running order has acts or runs out of applause to cut on, leaving at least `split_floor_s`
  on each side. Applause alone still does not end a part, since at a concert the audience applauds
  between pieces and the pieces carry that structure; a recording with no running order behaves
  exactly as before. On the opening of a research centre, 1 h 42 min with ten acts, the detector went
  from seven parts to ten, and the three boundaries it had been missing are the ones where a
  performance followed the applause rather than a speech.

- Acts are matched to the parts they were announced in, not to the printed order. The pipeline reads
  the transcript around each part boundary, two minutes back and a minute and a quarter forward, and
  asks `programme.align` which act was named there; `title_parts(..., assignments=...)` applies it,
  and a part where no name was heard keeps a generic title rather than borrowing one. Events run in
  a different order from their announcements: at the same opening, the printed order put both panels
  at the end, while the first panel came fourth and a percussion piece closed the evening. Against
  the recording, the names gave 5 of 10 parts correctly and 2 wrongly, where the printed order gave
  4 correctly and 6 wrongly.
- `avsegmenter cut`: one file per part from an analysis, each measured and brought to a loudness
  target. A part that is mostly speech is levelled first, since people at one microphone arrive at
  different levels; a part that is mostly music is given the gain and a limiter that should never
  engage, because its loudness range is content. `avsegmenter.mastering` holds the chain, the
  decision and the two ffmpeg passes, and `docs/loudness.md` the reasoning and the measurements.

- `avsegmenter captions` and `avsegmenter.captions`: WebVTT for any span of a recording, so a file
  cut out of it carries captions of its own. Cues are made into subtitles rather than left as
  transcriber segments: two lines of 42 characters, split where a segment runs long, de-overlapped,
  held no longer than seven seconds, and marked with the speaker where a voice takes over. On one
  defence 41% of the raw segments ran past two lines and 19% past seven seconds. `avsegmenter cut`
  writes one beside each part.
- `avsegmenter captions` takes a file joined from several spans of the recording, an opposition with
  a stop taken out of its middle, as `--span NAME=START:END+START:END` or `{"spans": [[start, end],
  ...]}` in the index, and keeps the captions in step with the cut: each span's cues start where
  the previous span's picture ends (`captions.cues_for_spans`).
- `examples/build_demo.py`: a demo folder built from an analysis, with a 720p proxy whose audio gets
  the treatment its kind deserves, the player, the report, the copied outputs and the index that
  lists the demos. The published demos had been assembled by hand and had drifted from the code.

### Fixed
- A voice arrives with its first exchange, not when it first holds the floor. An opponent opens with
  a greeting, a microphone check and a first question the candidate answers at length, and only
  some minutes in holds half of a five-minute window; the part boundary was landing there. The
  arrival is now the first of the speaker's own turns that lead up to the floor with no silence
  from that speaker longer than the window, while a lone question from the hall followed by a longer
  silence is still not an arrival. On one defence this had cut the second opposition in two, 5 min
  and 52 min, and left the running order with five parts to name from four acts.
- Acts are named by the names heard, not by the ordinary words in their titles: `musiscape.setlist`
  now matches a long title only as a phrase, drops a name two acts share, treats the parts of a
  defence as generic, and reads an introduction that names three or more acts as the programme
  being read out. On three defences the old scoring assigned 6 of 12 parts wrongly, and the new one
  assigns all 12 as the chair called them.
- The running-order table of `report.build_report` read the piece assignments whatever the
  programme was aligned to, so a talk, whose acts align to parts, reported every act as never
  performed. The table now reads the unit the programme was aligned to, and says which.
- The player asked for `crossorigin="anonymous"` on every video, which made a browser refuse to
  play a page opened from disk. Nothing in the player reads the video's pixels, so the attribute
  now goes on only when the media comes from another origin, where the text tracks need it.
- The caption track named Norwegian whatever language the transcript was in. The record carries
  the transcript language as `language`, the track names it, and a track whose language is unknown
  names none.
- The player's browser tab said "Concert segments" for every recording. It now carries the
  record's title, which `--title` sets.

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
- Report generator (`avsegmenter.report`) for a shareable HTML summary; `docs/render_page.py` for
  documentation pages in the same look.
- Look and feel after the UiO web profile (Helvetica/Arial, black normal-weight headings, underlined
  links) on the DAM palette (slate ground, white cards, swamp-green accent), light by default, no
  external fonts, overridable through custom properties on `.cs-root`.
- Quality and deposit: EBU R128 loudness, QC items (EBU Tech 3363 subset) as a PREMIS event, captions
  (WebVTT), derivatives manifest, JAMS export of the tiers, and a METS envelope with a timed structural
  map; standard audio descriptors with MPEG-7 names, picture brightness/saturation and a colourgram,
  motion-vector QoM from the codec, all as research tracks.
- Research layer: generic `research.tracks` (curve / state / image) and `research.tiers` (interval /
  point) in the record, an "Advanced view" in the player that draws them as lanes with deep links and
  CSV export, `avsegmenter add-track` / `add-tier` (ELAN .eaf, ELAN tab export, CSV) stored in
  `research_additions.json`, tiers exported as IIIF annotation pages and curves as CSV datasets.
