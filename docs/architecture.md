# Architecture

```
video ──► audio.extract_audio (MGT extract_wav) ──► 32 kHz / 22 kHz / 16 kHz caches
      │
      ├─► tagging.tag_frames (ambiscape.ml, PANNs)  ──► panns_frames.npz  (527 posteriors / 2 s)
      ├─► musicops.musiscape_songs / regions        ──► second opinion, boundary snapping
      ├─► fusion.fuse (musiscape.tagging chain)     ──► segments: music / speech / applause / silence / other
      ├─► level.ambiscape_features                  ──► 1 Hz level, novelty (sub-boundaries)
      ├─► speech (faster-whisper)                   ──► transcripts per segment, or one whole-file pass
      ├─► speakers.diarize (silero VAD + ECAPA)     ──► turns S0..Sn, roles         [when ≥ 5 min of talk]
      ├─► performers.detect_persons (MGT YOLO)      ──► persons.json
      ├─► camera.analyse_camera (MGT camera_motion) ──► camera.json: still / moving / cut, framings
      ├─► motion.motion_tracks (MGT, within budget) ──► QoM, videogram
      ├─► parts.find_parts                          ──► parts and breaks
      ├─► pieces / musicops.piece_descriptors       ──► instruments, genre, key, tempo, cues, fingerprint
      ├─► programme (musiscape.setlist)             ──► acts aligned to pieces or parts
      ├─► quality.loudness / quality.qc             ──► EBU R128, QC items (ffmpeg filters)
      ├─► features.audio_descriptors / picture_colour / motion_vectors ──► 1 Hz tracks (MPEG-7 names, colourgram, codec vectors)
      ├─► features.captions_vtt                     ──► captions.vtt from the transcript
      ├─► research.research_block (+ additions)     ──► research.tracks / research.tiers for the advanced view
      └─► metadata.probe + rights_block + derivatives ──► ffprobe facts, licence / privacy / copyrights, derivatives manifest
                                   │
                                   ▼
                     segments.json  +  curated.json
                                   │
        ┌──────────────────────────┼──────────────────────────┐
   player.html / segments-player.js   exports.record → ebucore / iiif + web annotations / schemaorg /
   chapters.vtt, captions.vtt,                        premis / jams / mets / tracks CSV / bag (BagIt)
   thumbs, videogram, motiongram,           report.build_report, docs/render_page.py
   one file per part, levelled              mastering.cut_parts (avsegmenter cut), docs/loudness.md
   colourgram
        research_additions.json  ◄── avsegmenter add-track / add-tier (ELAN, CSV)
```

Every stage caches its result in the output folder under a fixed name and skips itself when the file
exists, so a re-run after changing `curated.json` or a threshold takes about a minute. The heavy stages
(PANNs, YOLO, proxy, camera, Whisper, diarization embeddings) run once per recording.

Module map: `pipeline.run` orchestrates; `config.Config` holds every threshold; the analysis chain
(`fusion`, `speakers`, `parts`, `performers`, `camera`, `motion`, `level`, `musicops`, `pieces`, `speech`,
`fingerprint`, `programme`, `metadata`, `quality`, `features`, `research`) each does one thing; `export`
writes the web layer; `exports/` writes the standards (`record`, `ebucore`, `iiif`, `schemaorg`,
`provenance`, `jams`, `mets`, `bag`, `validate`, `writer`); `report` writes the summary page; `cli` is
the command with the `add-track`, `add-tier` and `refresh` subcommands.

Three files are contracts with people and other tools, and the analysis only reads them:
`curated.json` (what a person decided), `research_additions.json` (tracks and tiers added by
researchers or other software) and the programme file. Everything else is rewritten on every run.

The player has two levels: the main view (video, cut marks, videogram, waveform coloured by segment
with numbered pieces and part bands, speaker row, detail panel, metadata box) and the advanced view,
a collapsible box that renders whatever `research.tracks` and `research.tiers` contain. New analyses
therefore reach the page by writing to the record, not by changing the page.

Profiles (`concert`, `talk`) set only tuning defaults: minimum piece length, class weights. Nothing
structural depends on them; a lecture-recital gets its pieces and a concert gets its speaker turns.
