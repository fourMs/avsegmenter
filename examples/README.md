# Examples

Files from the two recordings the package was developed on, to copy and adapt.

| File | What |
|---|---|
| `curated-concert.json` | curated overlay for a concert: licence, privacy level, per-work rights status, organisation, URN namespace |
| `curated-defence.json` | curated overlay for a PhD defence: speaker names for the diarization clusters, rights |
| `programme-defence.json` | a running order as a JSON list of acts (a `.docx` table works too, see the README) |
| `make_report_concert.py`, `make_report_defence.py` | drivers for `avsegmenter.report.build_report` with the wording of each report |
| `prep_video_gpu.py` | proxy, camera analysis and people detection for a 36 GB 1080p50 file with `-hwaccel cuda` through MGT |

Typical runs:

```bash
avsegmenter concert.mp4 -o analysis --programme kjoreplan.docx --metadata curated-concert.json --bag
avsegmenter defence.mp4 -o analysis --profile talk --programme programme-defence.json --metadata curated-defence.json --no-checksum
avsegmenter add-tier analysis gestures.eaf          # a researcher's ELAN tier into the advanced view
avsegmenter add-track analysis hand_qom.csv --id hand_qom --label "Hand QoM" --unit a.u.
```
