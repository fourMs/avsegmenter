# Examples

Files from the two recordings the package was developed on, to copy and adapt.

| File | What |
|---|---|
| `curated-concert.json` | curated overlay for a concert: licence, privacy level, per-work rights status, organisation, URN namespace |
| `curated-defence.json` | curated overlay for a PhD defence: speaker names for the diarization clusters, rights |
| `programme-defence.json` | a running order as a JSON list of acts (a `.docx` table works too, see the README) |
| `make_report_concert.py`, `make_report_defence.py` | drivers for `avsegmenter.report.build_report` with the wording of each report |
| `build_demo.py` | build a demo folder from an analysis: a 720p proxy with the audio treated, the player, the report and the index that lists them |
| `prep_video_gpu.py` | proxy, camera analysis and people detection for a 36 GB 1080p50 file with `-hwaccel cuda` through MGT |

Typical runs:

```bash
avsegmenter concert.mp4 -o analysis --programme kjoreplan.docx --metadata curated-concert.json --bag
avsegmenter defence.mp4 -o analysis --profile talk --programme programme-defence.json --metadata curated-defence.json --no-checksum
avsegmenter add-tier analysis gestures.eaf          # a researcher's ELAN tier into the advanced view
avsegmenter add-track analysis hand_qom.csv --id hand_qom --label "Hand QoM" --unit a.u.
avsegmenter cut analysis --stem laczko               # one file per part, levelled and normalised
```

Rebuilding a demo, which is how the published demos are kept level with the code:

```bash
python examples/build_demo.py demo/defence --analysis ../defence/analysis --video ../defence/output.mp4 \
  --title "Public PhD defence" --subtitle "3 h 24 min, four parts" --date 2026-08-19
python examples/build_demo.py demo/concert --analysis ../concert/analysis --keep-video   # pages only
```
