# The record: `segments.json`, `curated.json`, `record.json`

## `segments.json` (automatic; rewritten on every run)

| Key | Content |
|---|---|
| `title`, `profile`, `generated`, `tools`, `config` | run facts: title, tuning profile, timestamp, toolbox versions, thresholds |
| `video` | `file`, `duration`, `url`, `width`, `height`, `tech` (ffprobe: container, size_bytes, duration_s, bitrate_kbps, created, video_codec, profile, fps, pix_fmt, bit_depth, color, audio_codec, sample_rate_hz, channels, channel_layout, audio bitrates and depth) |
| `segments[]` | `id`, `kind` (music / speech / applause / silence / other), `start`, `end`, `duration`, `confidence`, `title`, `thumbnail`, `level` (Leq/L10/L90 dBFS), `motion` (QoM share, still-camera seconds), `transcript`, `piece_index`, `part_index` |
| `pieces[]` | one per music segment: `index`, `title`, `start`, `end`, `plan` (matched act), `performer_names_guess`, `performers` (estimate/low/high, framings, method, stage_filter), `ensemble`, `instruments[]` and `genres[]` (AudioSet label + posterior), `singing_p`, `top_tags`, `music` (tempo_bpm, pulse_R, key, key_conf, dyn_range_db, … with `tempo_reliable`/`key_reliable`), `level`, `motion`, `camera` (shots, cuts, framings, moving_share), `sub_boundaries`, `internal_cues`, `intro` (the introduction's segment and transcript), `rights` (fingerprint, AcoustID matches, note), `part_index` |
| `parts[]` | `kind` (part / break), `index`, `start`, `end`, `duration`, `title`, `cues` (start / break / break-end / applause / speaker:Sx), `content_share`, `speech_share`, `speakers` (share of the floor), `performers`, `camera`, `plan`, `pieces` (indices inside) |
| `speakers` | `speakers{Sx: total_s, first_at, turns, name, role}`, `roles`, `turns[]` (`speaker`, `start`, `end`, `text`) |
| `camera` | `hop_s`, `cuts[]`, `summary` (still / moving / cut shares), `n_shots` |
| `tracks` | `level_db` at 1 Hz, `qom` at 1 Hz (camera motion masked) |
| `programme` | the loaded acts, `aligned_to` (pieces / parts), `assignments`, `not_detected` |
| `metadata` | the rights block as merged from `curated.json`: `license`, `license_url`, `rights_holder`, `privacy` (`level`, `reasons`, `note`, `suggested`), `copyrights[]`, `notes` |
| `hierarchy`, `summary`, `videogram` | counts per level, seconds per class, the videogram file |
| `quality` | `loudness` (EBU R128: `integrated_lufs`, `loudness_range_lu`, `true_peak_dbtp`, `momentary_lufs_1hz`) and `qc` (items with `id`, `outcome` pass / warning / info / not measured, counts and spans) |
| `features` | summaries of the standard feature runs (`audio` with MPEG-7 names, `colour`, `motion_vectors`); the series themselves are research tracks |
| `derivatives[]` | every derived file: `path`, `mimetype`, `size_bytes`, `sha256`, `generator`, `role` |
| `captions` | `captions.vtt` when a transcript exists |
| `research` | `tracks[]` (`id`, `label`, `kind` curve/state/image, `unit`, `hop_s`, `values`/`states`/`image`, `source`, `range`, `palette`) and `tiers[]` (`id`, `label`, `kind` interval/point, `source`, `items[]` with `start`, `end`, `label`, `attrs`, `confidence`); built-in entries are recomputed each run, entries from `research_additions.json` are kept |

## `curated.json` (human; never written by the analysis)

All keys optional. Anything here wins over the automatic value and is listed in the record's provenance.

| Key | Meaning |
|---|---|
| `title`, `description`, `date` (ISO), `venue`, `organisation`, `organisation_url`, `language` (ISO 639), `keywords[]` | descriptive |
| `identifier`, `urn_prefix` | the persistent id of the recording; the namespace for local ids (default `urn:avsegmenter`) |
| `people[]` | `{name, role, affiliation, identifier}`; roles from the EBU role list: performer, composer, lyricist, conductor, presenter, lecturer, candidate, opponent, chair, committee, supervisor, organiser, camera, producer |
| `license`, `license_url`, `rights_holder` | licence of the recording |
| `privacy` | `"green" \| "yellow" \| "red"` or `{level, note}`; without it a *suggested* level with reasons is shown |
| `copyrights[]` | `{nr \| piece \| work, status, note, work, composer, performers}`; keyed by plan number; overrides the pre-filled entries |
| `access` (`open` / `restricted`, default restricted), `embargo_until` | access |
| `speakers` | `{Sx: "Name (role)"}` for the diarization clusters of this run |
| `notes` | free text shown in the metadata box |

## `research_additions.json` (human or other tools; never written by the analysis)

`{"tracks": [...], "tiers": [...]}` in the same shapes as above, written by `avsegmenter add-track` and
`avsegmenter add-tier` (with `added` timestamp and `author`). Edit or delete entries freely.

## `record.json` (canonical, generated)

`schema: urn:avsegmenter:record:1.0`. Five layers: `descriptive`, `technical`, `structural` (`items` = parts and pieces with `kind`, `segments`, `turns`, `speakers`, `camera`, `tracks`), `rights`, `provenance` (software and models, parameters, `curated_fields`). Every export in `export/` is a pure function of this record; see `metadata-approach.md` for the standards and `../avsegmenter/exports/` for the mappings.
