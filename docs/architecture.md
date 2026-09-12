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
      └─► metadata.probe + rights_block             ──► ffprobe facts, licence / privacy / copyrights
                                   │
                                   ▼
                     segments.json  +  curated.json
                                   │
        ┌──────────────────────────┼──────────────────────────┐
   player.html / segments-player.js   exports.record → ebucore / iiif / schemaorg / premis / bag
   chapters.vtt, thumbs, videogram         report.build_report
```

Every stage caches its result in the output folder under a fixed name and skips itself when the file
exists, so a re-run after changing `curated.json` or a threshold takes about a minute. The heavy stages
(PANNs, YOLO, proxy, camera, Whisper, diarization embeddings) run once per recording.

Module map: `pipeline.run` orchestrates; `config.Config` holds every threshold; the analysis chain
(`fusion`, `speakers`, `parts`, `performers`, `camera`, `motion`, `level`, `musicops`, `pieces`, `speech`,
`fingerprint`, `programme`, `metadata`) each does one thing; `export` writes the web layer; `exports/`
writes the standards; `report` writes the summary page; `cli` is the command.

Profiles (`concert`, `talk`) set only tuning defaults: minimum piece length, class weights. Nothing
structural depends on them; a lecture-recital gets its pieces and a concert gets its speaker turns.
