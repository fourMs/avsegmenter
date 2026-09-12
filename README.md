# concert-segmenter

Splits a concert video into **pieces, applause, spoken introductions and silence**, describes each
piece (instruments, genre tags, singing, tempo/key, performer count, motion), and exports a
web timeline that can sit under the video on the DAM catalog page
(`https://dam.hf.uio.no/catalog/imv/<id>`).

Built from three UiO toolboxes, each used for what it is best at:

| Toolbox | Functions used | Role |
|---|---|---|
| **musicalgestures (MGT)** | `extract_wav`, `_tracks.extract_tracks_parallel`, `_tracks.read_columns`, `_performers.detect_people` / `performer_count` | audio extraction; whole-concert quantity of motion and videograms; people on stage with the audience filtered out |
| **ambiscape** | `ml.tag_frames` (PANNs CNN14 / AudioSet 527, `device="auto"`), `open_recording`, `extract_session`, `load_features`, `segmentation.segment` | frame-wise posteriors; 1 Hz level features; novelty boundaries inside long sets |
| **musiscape** | `tagging.*` (the segmentation chain incl. `absorb_other`, `snap_to_songs`, `refine_music_onsets`), `setlist.load_setlist` / `align_setlist` / `act_title`, `concert.find_songs`, `concert.classify_regions`, `features.extract_track`, `figures.concert_timeline` | segments from the posteriors, setlist alignment, second-opinion song finder, per-piece key/tempo/dynamics, overview PNG |

The segmentation chain, the setlist alignment and the performer counting were developed here and
upstreamed (fourMs/ambiscape#12, fourMs/MGT-python#381 and #382, musiscape PR); this package is the
glue, the caches and the web export.

Plus optional: **ultralytics YOLO** (people on stage), **faster-whisper** (transcribe the introductions),
**ffmpeg chromaprint** (+ AcoustID if you supply a key).

## Run

```bash
pip install -e .                      # package is a thin layer over the three toolboxes
concert-segment concert.mp4 -o analysis \
    --title "Semesterstartkonsert H26" \
    --video-url "https://dam.hf.uio.no/api/public/media?id=20162&library=imv" \
    --whisper-python ~/.venvs/annotate-audio/bin/python   # any interpreter with faster-whisper
# stages can be skipped: --skip video,speech,fingerprint ; --device cpu works, just slower
# with a running order (IMV "kjøreplan" .docx table, or a JSON list of acts):
concert-segment concert.mp4 -o analysis --programme Kjoreplan.docx
# with license / privacy level / known copyrights for the metadata box:
concert-segment concert.mp4 -o analysis --programme Kjoreplan.docx --metadata metadata.json
```

`metadata.json` holds what the analysis cannot know: `license` (+ `license_url`, `rights_holder`),
`privacy` (`green` / `yellow` / `red`, with a `note`; without it the page shows a *suggested* level with
its reasons, e.g. audience visible, performers named) and `copyrights`, a list keyed by plan number
(`{"nr": "9", "status": "protected", "note": "..."}`) that overrides the entries pre-filled from the
programme. Technical facts (container, size, duration, resolution, frame rate, pixel format and bit
depth, codecs, bitrates, sample rate, creation time) come from ffprobe automatically.

`--programme` aligns detected pieces to the planned acts: names heard in the spoken introduction are
fuzzy-matched against act / performers / work / composer (thank-yous to the previous act are ignored,
names right after "vær så god" or "ved" count extra), pieces that name nobody are placed by running order or
continue the previous act, and acts that never appear are listed under `programme.not_detected`
(cancelled, or not a musical number). Each piece records how it was matched (`name`, `order`, `continues`).

Everything is cached in the output directory (PANNs frames, YOLO boxes, MGT tracks, transcripts),
so re-running after a threshold change takes seconds.

## Talk-heavy recordings (`--profile talk`)

A PhD defence, a seminar or a panel is one long speech segment to a sound-event tagger. The
`talk` profile keeps the same segmentation but adds who spoke when and how the event was structured:

```bash
concert-segment defence.mp4 -o analysis --profile talk --programme programme.json --metadata metadata.json
```

- **Speakers** (`speakers.py`): silero VAD → 1.5 s windows → ECAPA-TDNN embeddings (speechbrain, GPU)
  → agglomerative clustering (cosine; `--speakers N` fixes the count) → smoothed turns `S0, S1, …`
  ordered by speaking time. Roles are *suggested* (first voice = chair, most speaking = candidate,
  next long voices = opponents); name them in `metadata.json` under `"speakers": {"S0": "…"}`.
- **Parts** (`parts.py`): boundaries at long non-speech gaps (breaks), applause bursts and a change of
  the dominant speaker; short parts merge; a part that is mostly non-speech is a break. Titles come
  from `--programme` by running order (a JSON list of acts).
- **Transcript**: a whole-file `whisper_full.json` in the output folder is reused (one Whisper pass
  over three hours is cheaper than hundreds of short ones); otherwise the speech segments are
  transcribed as in the concert profile. Text is attached to turns and segments.
- **Video**: MGT motion tracks are skipped for hours of 1080p; the proxy, camera analysis and people
  count run as usual. Pass ffmpeg `-hwaccel cuda` through MGT's detectors for big files (see
  `analysis/prep_video.py` in the defence example).
- **Player**: parts are numbered instead of pieces, a speaker row shows the turns in colour, the
  legend lists speakers with roles and speaking time, and the detail panel shows the current part,
  who is speaking and what they said.

## Standard metadata exports (`analysis/export/`)

Every run also writes the standard views of the result, generated from `segments.json` plus the curated
overlay (`curated.json`, formerly `metadata.json`): **EBUCore 1.10** (`ebucore.xml`, the master archival
record), **IIIF Presentation 3** (`manifest.json`, ranges for pieces/parts and annotation pages for
segments, speaker turns and camera cuts), **W3C Web Annotation** (`annotations.json`), **schema.org**
JSON-LD (`schemaorg.json`), **PREMIS 3** provenance (`premis.xml`), WebVTT chapters, and the canonical
`record.json`. `--bag` adds a **BagIt 1.0** bag for deposit with the video hard-linked. `--base-url` sets
the public folder the DAM serves from (IIIF ids), `--identifier` the persistent id. `validation.json`
lists the checks; EBUCore and PREMIS validate against the XSDs when they are in `~/.cache/av-xsd` or
`$AV_XSD_DIR`. See `docs/METADATA-APPROACH.md` for the one-page description written for HUMIT.

## Outputs (`analysis/`)

| File | What |
|---|---|
| `segments.json` | the whole result: `segments[]` (kind, start, end, confidence, title, thumbnail, level, motion, transcript), `pieces[]` (see below), `summary`, musiscape's own `songs`/`regions`, tool versions |
| `chapters.vtt` | WebVTT chapters; can be attached to any `<video>` as `<track kind="chapters">` |
| `player.html` | self-contained player: video; camera-cut marks, MGT videogram strip and a waveform coloured by segment with the pieces numbered; a detail panel for the segment under the playhead (programme entry, performers, camera, instruments, intro transcript); a collapsible box with technical metadata, license, privacy level and known copyrights; light/dark mode with a toggle; clicking a piece starts 2 s before its first note; `[`/`]` jump between pieces |
| `timeline.png` | musiscape overview strip (labels + level) |
| `videogram.png` | MGT vertical videogram of the whole concert |
| `thumbs/` | one keyframe per segment |

Each **piece** carries: `performers` (`estimate`, `low`, `high`, counted per still camera framing),
`camera` (shots, cuts, share of time the camera was moving),
`ensemble` hint, `instruments` and `genres` (mean AudioSet posteriors), `singing_p`, `music`
(musiscape: `tempo_bpm`, `pulse_R`, `key`, `key_conf`, `dyn_range_db`, … with `tempo_reliable` /
`key_reliable` gates), `level` (Leq/L10/L90 dBFS from ambiscape), `motion` (MGT QoM relative to the
concert maximum, with camera moves and cuts masked out), `sub_boundaries` (ambiscape novelty peaks inside long sets), `intro` (the preceding
talk segment and its transcript), `performer_names_guess` (names heard in the intro) and `rights`.

## How the segmentation works

1. PANNs posteriors every 2 s (4 s window) through `ambiscape.ml.tag_probabilities`.
2. Group max: music = {Music, Musical instrument, Singing, Choir, A capella, Piano, Guitar, Synthesizer, …},
   speech = {Speech, Male/Female speech, Narration, Conversation}, applause = {Applause, Clapping, Cheering, Crowd}.
3. Weighted argmax per frame (applause ×1.6 because it is short and quiet), RMS < −60 dBFS ⇒ silence,
   nothing above 0.25 ⇒ other. 10 s majority filter, then minimum durations
   (music 20 s, speech 6 s, applause 4 s, silence 10 s) absorb blips into the longer neighbour.
4. Music edges are snapped to `musiscape.concert.find_songs` boundaries when the two agree within 6 s.
5. Within pieces longer than ~2 min, `ambiscape.segmentation.segment` proposes internal change points
   (song changes inside a band set, movements inside a piece). These are shown as *candidates* only.

Tests: `python -m pytest tests` (covers the fusion chain with synthetic data).

## What can and cannot be answered automatically

| Question | Answer | How reliable |
|---|---|---|
| Music / applause / talk / silence boundaries | yes | good on this material; applause bursts of 5–15 s are found; the participatory "mobile orchestra" part comes out as alternating talk/music, which is honest |
| Number of performers | YOLO person boxes (MGT `detect_people`), audience filtered by position (`on_stage`), counted per *framing*: camera cuts and PTZ moves are detected on the proxy video (`camera.py`), and each still run of ≥10 s gives one count (its 75th percentile); the widest framing is the estimate, the tightest is `low` | exact for 1–5 on stage on the H26 concert; choirs are under-counted (occlusion, 7 of 17) |
| Instruments | AudioSet posteriors (piano, guitar, synthesizer, drum kit, choir, singing…) | fine for dominant instruments; double bass vs bass guitar and similar pairs are weak; nothing on how many of each |
| Genre | AudioSet genre tags (classical, jazz, rock, electronic, gospel…) | coarse and biased to mainstream genres; treat as tags, not a classification |
| Which piece / composer | **not from the audio alone.** With `--programme`, the running order is aligned to the detected pieces via the introductions (9/9 correct on the H26 concert, including two cancelled acts and a reordered programme); without it, The transcript of the spoken introduction is attached to each piece and names are extracted heuristically; the programme must confirm | Whisper large-v3 on Norwegian: names are often misheard |
| Copyrighted music | Chromaprint fingerprints are computed and can be looked up in AcoustID (`--acoustid-key`). Live performances almost never match released recordings, so **a miss is not evidence of anything**. Work-level rights (composer death + 70 years) need the work title; performers' rights on the recording exist regardless | hint only |

## Adding it to the DAM page

The catalog page is a Next.js app that renders `<video controls playsInline poster … className="w-full rounded-xl shadow bg-black">`
with the signed media URL as its `<source>`. Two integration levels:

**A. Zero-code (chapters only).** Publish `chapters.vtt` next to the asset and add
`<track kind="chapters" src=".../chapters.vtt" srclang="no" default>` to that `<video>`.
Browsers expose chapters through the native controls / accessibility tree.

**B. Timeline component.** Publish `segments.json` + `thumbs/` next to the asset (e.g.
`collections/imv/20162/analysis/`), ship `web/dam-segments.js` as a static file, and in the client
component that owns the video:

```tsx
'use client';
import { useEffect, useRef } from 'react';
export default function SegmentTimeline({ videoRef, base }: { videoRef: React.RefObject<HTMLVideoElement>, base: string }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!videoRef.current || !box.current) return;
    const s = document.createElement('script'); s.src = '/js/dam-segments.js';
    s.onload = () => (window as any).ConcertSegments.mount({
      video: videoRef.current, url: `${base}/segments.json`, container: box.current, assetBase: `${base}/` });
    document.body.appendChild(s);
  }, [videoRef, base]);
  return <div ref={box} className="mt-4" />;
}
```

`mount()` draws the coloured strip, the videogram and waveform strips (from `data.videogram` and
`data.tracks.level_db`), a legend with per-class toggles and a detail panel that follows the playhead;
clicking a piece seeks `preroll` seconds (default 2) before its start. It binds `[` `]` `n` `p`. It only needs
the `<video>` element; it does not care where the media comes from. Styles are injected once under
the `.cs-` prefix and pick up dark backgrounds; override the `--cs-*` custom properties for the DAM look.

The analysis itself is meant to run server-side once per upload (GPU: ~3 min for a 90-min concert
excluding MGT motion tracks, which take ~10 min on 6 cores; CPU-only PANNs is ~30 min).
