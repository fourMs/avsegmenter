"""Shareable report for the defence recording (talk profile)."""
from pathlib import Path
from concert_segmenter.report import build_report
QA = [
    ("Parts of the event", "Yes", "yes",
     "Boundaries from silences longer than 90 s (breaks), applause bursts, and the first sustained turn of a new major voice. The four detected parts match the four hand-cut recordings (trial lecture, thesis introduction, first opponent, second opponent) to within a minute or two; the chair's opening words attach to the part they introduce."),
    ("Who is speaking", "Estimate", "part",
     "silero VAD, ECAPA speaker embeddings (speechbrain) on 1.5 s windows, agglomerative clustering with small clusters folded into the nearest voice. Four voices came out and were named by hand: candidate, chair, first and second opponent. Question marks in the transcript sit with the opponents' turns, as they should. Short interjections from the audience are absorbed into the nearest main voice."),
    ("What was said", "Transcript", "yes",
     "One Whisper large-v3 pass over the whole recording (language detected automatically), attached to each speaker turn; shown in the detail panel of the player."),
    ("Camera and people", "As for concerts", "part",
     "Camera cuts and PTZ moves from the proxy; people counted per still framing. Decoding 36 GB of 1080p50 is the slow part; MGT's motion tracks are skipped for a recording of this length."),
    ("Music", "Rare", "part",
     "The sonification demos inside the trial lecture score as 'other' rather than music and are kept inside the part; the talk profile does not split a part on them."),
]
html = build_report(Path(__file__).parent, title="Public defence, segmented", eyebrow="IMV · Forsamlingsalen · 19 August 2026 · Bálint Laczkó", qa=QA)
html = html.replace("<title>Public defence, segmented</title>", "<title>Laczkó Defence Segments</title>")
Path(__file__).parent.joinpath("report.html").write_text(html); print("report.html", len(html))
