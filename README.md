# avsegmenter

Segment audio–video recordings of events, concerts, lectures, PhD defences, panels, into parts,
pieces, speaker turns and segments, describe each, and export a web player and standard archival
metadata. Runs locally; nothing leaves the machine unless you ask it to.

Built on three toolboxes from the fourMs lab at the University of Oslo:
[musicalgestures (MGT)](https://github.com/fourMs/MGT-python) for the video side,
[ambiscape](https://github.com/fourMs/ambiscape) for sound-event tagging and level features,
[musiscape](https://github.com/fourMs/musiscape) for the music side and the segmentation chain.

## What you get

For one recording, one folder:

| | |
|---|---|
| `segments.json` | everything found: segments (music / talk / applause / silence / other), pieces with instruments, genre tags, key and tempo, people on stage; parts; speaker turns with transcript; camera cuts; technical facts |
| `player.html` | self-contained player: video, camera-cut marks, MGT videogram, waveform coloured by segment, part bands and numbered pieces, speaker row, detail panel, metadata box, light/dark |
| `segments-player.js` | the same timeline as a drop-in for any HTML5 `<video>` (`SegmentsPlayer.mount({video, url, container})`) |
| `chapters.vtt`, `thumbs/`, `videogram.png` | for other players |
| `export/` | EBUCore 1.10 (validated), IIIF Presentation 3 + Web Annotations, schema.org JSON-LD, PREMIS 3, JAMS, METS, the canonical `record.json` |
| `bag/` (`--bag`) | a BagIt 1.0 bag for deposit, media hard-linked |

## Install

```bash
pip install -e .                       # plus the three toolboxes and their [ml] extras
pip install ultralytics speechbrain av # people detection, speaker turns, codec motion vectors
# transcripts: any interpreter with faster-whisper, passed with --whisper-python
```

ffmpeg with Chromaprint must be on the path. A GPU makes the PANNs, YOLO, Whisper and ECAPA stages
fast (an 87-minute concert: about three minutes plus MGT motion tracks); CPU works, slower.

## Run

```bash
avsegmenter concert.mp4 -o analysis --programme kjoreplan.docx --metadata curated.json
avsegmenter defence.mp4 -o analysis --profile talk --programme acts.json --metadata curated.json --no-checksum
avsegmenter cut analysis --stem laczko          # one file per part, levelled, with its own .vtt
avsegmenter captions analysis --index trim/parts.json   # captions for files cut elsewhere
```

`avsegmenter cut` writes one file per part from an analysis, each measured and brought to a
loudness target, with the treatment the part deserves. A part that is mostly speech is levelled
first, because people sharing one microphone in a room arrive at different levels: on the two
defences the voices spanned 10.9 LU, several of those inside a single part. A part that is mostly
music is given the gain and a limiter that should never engage, and nothing else, since its dynamics
are the content. `--target` moves the target from the web figure of -16 LUFS to broadcast delivery
at -23; `--plain` turns the levelling off everywhere. See `docs/loudness.md`.

Each file gets a `.vtt` of its own, since the transcript is timed against the whole recording and a
part cut out of it starts at zero. `avsegmenter captions` does the same for files cut with something
else, from an index or from `--span NAME=START:END`. The cues are subtitles rather than transcriber
output: wrapped to two lines of 42 characters, split where a segment runs past that or past seven
seconds, never overlapping, and carrying the speaker's name where a new voice takes over.

Options: `--profile concert|talk` (tuning defaults only), `--programme` (a `.docx` running-order table or
a JSON list of acts), `--metadata curated.json` (what a person decided; never overwritten),
`--speakers N`, `--diarize auto|always|never`, `--video-url`, `--base-url` and `--identifier` (for the
exports), `--bag`, `--no-checksum`, `--motion-tracks`, `--skip video,speech,fingerprint,speakers,export`,
`--whisper-python`, `--device`.

Python:

```python
from pathlib import Path
from avsegmenter import Config
from avsegmenter.pipeline import run
from avsegmenter.exports import write_all

data = run(Path("concert.mp4"), Path("analysis"), Config(profile="concert"), programme_path="kjoreplan.docx")
rec = write_all(Path("analysis"), Path("concert.mp4"), base_url="https://example.org/rec/1", bag=True)
```

## One hierarchy for every recording

Concerts have talk in them and lectures have music in them, so nothing is gated by the profile.
Parts are cut at long silences (breaks), at applause that is followed by talk, where a voice
arrives that then holds the floor, and at the title cards on the projection where the slides have been
read (`--slides`, optional, needs easyocr). A card is the surest boundary there is: it changes when
the act changes, and while it is up the act is running, so a change of voice inside its span does not
cut. Where a running order is given, the number of acts in it is the
number of parts to look for: a recording that comes out short is split again at the applause inside
its longest parts, strongest burst first. That is what a mixed event needs, where a contribution is
applauded and a performance follows rather than a speech, and it leaves a concert alone, since there
the pieces carry the structure and the parts are the halves around the interval. Pieces are the music
segments. Speaker turns come from diarization whenever there are five minutes of talk. Segments are
the raw classes. A concert without an interval is one part with its pieces and the host's turns; a
defence is four parts with any demos as pieces; a lecture-recital alternates turns and pieces inside
one part.

People on stage are counted per still camera framing (MGT `camera_motion` + `performer_count`): the
widest framing for a piece, the typical one for a talk part; the audience filter is on when the
detections show a raised stage. Programme acts go to pieces when music dominates and to parts
otherwise, matched either way on the names heard in the introductions, with thank-yous ignored: the
transcript around a part boundary says which act was announced there. Events run in a different order
from their announcements often enough that the words in the room are the better witness, and a part
where no name was heard keeps a generic title rather than borrowing one. Where there is no
transcript, parts fall back to the running order. Acts that were never announced are reported.

## How the segmentation works

PANNs posteriors every 2 s (`ambiscape.ml.tag_frames`) → group max per class (choir, singing and the
common instruments count as music) → weighted decision with a level gate → majority filter → run-length
spans → per-class minimum durations → loud non-speech beside music is the piece → snap to musiscape's
song finder → move each piece's start back to the first sound. The chain lives in `musiscape.tagging`.

## What it can and cannot tell you

| Question | Answer | Reliability on the two test recordings |
|---|---|---|
| Music / talk / applause / silence | yes | all nine acts of a concert; the four parts of a 3 h 24 min defence within a minute or two of hand-cut reference recordings |
| Which piece, who performs | from the spoken introductions aligned with the programme | 9 of 9 on the concert, including two cancelled acts and a reordered programme |
| Who is speaking | diarization, roles suggested, names from `curated.json` | four voices in the defence; short interjections merge into the nearest voice |
| How many on stage | detector + camera framings | exact for soloists, a duo and a five-piece band; a 17-voice choir under-counted (7); 1, 1, 2, 2 for the defence |
| Instruments, genre | AudioSet tags | dominant instruments reliable; bass guitar vs double bass weak; genre tags coarse |
| Copyright | fingerprints + the programme | live performances do not match released recordings; the works list decides; rights status is curated |

## Look and feel

The player, the reports and the documentation pages follow the University of Oslo web profile and the
DAM application it will sit in: Helvetica/Arial with black, normal-weight headings and underlined
links, a slate ground with white cards and a swamp-green accent, no external fonts. The player is
light by default with a dark toggle. Everything is driven by CSS custom properties (`--cs-fg`,
`--cs-card`, `--cs-border`, `--cs-accent`, `--cs-mark`, …) on the container, so another institution
changes the look by setting those on `.cs-root`. `docs/render_page.py` renders a Markdown page in the
same look.

## Documentation

- `docs/architecture.md`: stages, caches, module map
- `docs/record-schema.md`: every field of `segments.json`, `curated.json`, `record.json`
- `docs/metadata-approach.md`: the standards (EBUCore, IIIF, schema.org, PREMIS, BagIt) and the five layers
- `docs/integration-dam.md`: attaching the output to a catalog, with the UiO DAM as the worked case
- `examples/`: curated and programme files, report drivers and a GPU-decode prep script from the two test cases
- `CHANGELOG.md`

Tests: `python -m pytest tests` (fusion, parts, roles, stage detection, research importers, loudness and
QC parsing, captions, and the exports incl. EBUCore structure, IIIF shape, JAMS, METS and bag integrity).

## Licence

MIT. Developed for the Department of Musicology, University of Oslo; nothing in the library assumes
that deployment (identifiers, organisation and provider come from `curated.json`).
