"""Build the shareable report for this concert (IMV-specific wording lives here, the generator is generic)."""
from pathlib import Path
from concert_segmenter.report import build_report

QA = [
    ("Music / clapping / talking", "Yes", "yes",
     "AudioSet posteriors every 2 s (PANNs CNN14 through <code>ambiscape.ml.tag_frames</code>), turned into segments by <code>musiscape.tagging</code>. All nine acts, their applause and the spoken introductions come out; the participatory mobile-orchestra number alternates talk and short sound bursts, which is what it was. Each piece starts where its sound begins, not where the tagger first noticed it."),
    ("Which pieces", "With the plan", "yes",
     "Names in the transcribed introductions are matched to the running order (<code>musiscape.setlist</code>): 9 of 9 pieces land on the right act, the two cancelled acts and the reordering are found. Without a plan, only the misheard names from Whisper remain (“Åsle Vattene”, “Terstas Winner”)."),
    ("Camera changes and PTZ", "Handled", "yes",
     "<code>musicalgestures.camera_motion</code> labels each half second still, moving or cut from the global geometry between frames: 14% of this recording is camera movement and there are 25 cuts. Performer counts are read per still framing, and camera motion is left out of the motion measure."),
    ("How many perform", "Estimate", "part",
     "YOLO person boxes at 1 fps (<code>musicalgestures.detect_people</code>), audience removed by position, one count per still framing, the widest framing counting. Exact for the soloists, the duo and the five-piece band; the choir is under-counted (7 of about 17) because singers occlude each other."),
    ("Instruments", "Dominant only", "part",
     "Piano, choir, synthesizer, guitar and singing are tagged confidently. Double bass and drum kit in the duo and the band are missed or weak; the laptop pieces get no instrument tag at all."),
    ("Genre", "Tags, not a label", "part",
     "Classical for the piano pieces, gospel/vocal for the choir, electronic for the synthesizer set, rock for the band. AudioSet's genre vocabulary is coarse and mainstream-biased."),
    ("Songs inside a set", "Cues only", "part",
     "Quiet moments and talking inside a piece are listed as song-change cues; Gravel Peak's pause at 81:46 and Tejaswinee's at 70:57 are real changes, but Erik's two standards ran together with no audible break."),
    ("Copyrighted music", "Not decidable from audio", "nov",
     "Chromaprint fingerprints are computed per piece and can be looked up in AcoustID, but live performances do not match released recordings, so a miss proves nothing. With the plan the works are known, and that is what decides it: Backer Grøndahl (d. 1907) is public domain; the Ellington (d. 1974) and Rodgers (d. 1979) standards are still protected and need clearance for online publication beyond a concert licence; Crome Hill, Vincenzo, Fredrik, Tejaswinee and Gravel Peak perform their own works and can consent themselves. Performers' rights on the recording exist in every case."),
]
NOTES = {"1": "cancelled (Kristina did not perform)",
         "2": "participatory number with the audience's phones, 11:25–17:59; detected as talk with short sound bursts, not as a music piece",
         "5": "cancelled (Kristina did not perform)",
         "6": "two songs, second with audience sing-along and piano",
         "9": "two standards, no audible break between them",
         "10": "plan lists three pieces; one clear internal pause at 70:57",
         "11": "5 on stage, plan lists 6 (Maria Kverno absent?)"}
html = build_report(Path(__file__).parent, title="Semesterstartkonsert H26, segmented",
                    eyebrow="IMV · Salen · 24 August 2026 · DAM asset imv/20162", qa=QA, notes=NOTES)
html = html.replace("<title>Semesterstartkonsert H26, segmented</title>", "<title>Semesterstartkonsert H26 Segments</title>")
Path(__file__).parent.joinpath("report.html").write_text(html)
print("report.html", len(html))
