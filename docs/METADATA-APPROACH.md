# Metadata for IMV's audio-visual recordings: the approach

*For HUMIT. One page on what the analysis produces, which standards it speaks, and what the DAM needs to do with it.*

## What we have

`avsegmenter` analyses a recording once, on our own servers, and writes an **analysis folder** next to it:

- `segments.json` — everything the analysis found (automatic; overwritten on every run)
- `curated.json` — what a person decided (title, people and roles, license, privacy level, per-work rights status, speaker names; never written by the analysis)
- `player.html`, `chapters.vtt`, `thumbs/`, `videogram.png` — the web layer
- `export/` — the standard metadata, generated from the two JSON files above:

| File | Standard | Purpose |
|---|---|---|
| `ebucore.xml` | **EBUCore 1.10** (EBU Tech 3293) | the master archival record: descriptive, technical, structural (parts, segments, speaker turns, camera cuts), rights, provenance summary. Maps to Dublin Core, PBCore, schema.org and MPEG-7 AVDP when a depositary asks for one of those |
| `manifest.json` | **IIIF Presentation 3** | a Canvas for the recording, Ranges for pieces/parts (table of contents), annotation pages for segments, speaker turns and cuts; any IIIF A/V viewer plays it |
| `annotations.json` | **W3C Web Annotation** | the same time-anchored annotations as a plain collection (media fragments `#t=start,end`) |
| `schemaorg.json` | **schema.org** `VideoObject` + `MusicEvent`/`EducationEvent` | JSON-LD for the catalog page head: search engines, UiO's discovery layer |
| `premis.xml` | **PREMIS 3** | provenance: which software versions and models produced which layer, with parameters and the file's SHA-256 |
| `chapters.vtt` | **WebVTT** | chapters for any HTML5 player |
| `record.json` | internal canonical record (schema `urn:avsegmenter:record:1.0`) | the single source all of the above are generated from |

`--bag` additionally writes a **BagIt 1.0** bag (RFC 8493): `data/` with the video (hard-linked, not copied), the exports and the web layer, SHA-256 manifests and `bag-info.txt`. That is the deposit unit for the National Library, DUO or any repository that takes bags.

## Five layers, one rule

1. **Descriptive** — title, date, venue, organisation, people with roles, works, genre, language.
2. **Technical** — container, codecs, resolution, frame rate, pixel format and bit depth, audio layout, bitrates, size, creation time, SHA-256 (ffprobe).
3. **Structural** — music / talk / applause / silence segments with confidence; pieces or parts with start and end; speaker turns with transcript; camera cuts and moves.
4. **Rights and access** — licence, rights holder, privacy level (green / yellow / red with a reason), per-work copyright status, access (`open` / `restricted`), embargo.
5. **Provenance** — tool and model versions, parameters, which fields a person set.

The rule: **the analysis fills layers 2 and 3 and proposes 1 and 4; a person confirms 1 and 4 in `curated.json`; a re-run never overwrites a curated value.** Every record says which fields were curated.

Classes use controlled vocabularies, not free text: AudioSet ontology ids for sound classes and instruments, EBU role and genre labels, MPEG-7 CameraMotion terms, ISO 639 for languages, and local URNs for the recording, the segment classes and the part kinds under a namespace the deployment chooses (`urn_prefix` in `curated.json`; UiO uses `urn:uio:imv`).

## What the DAM needs to do

1. **Store the analysis folder next to the asset** (for asset 20162: `collections/imv/20162/analysis/`), and serve it as static files. Nothing in it is large except thumbnails.
2. **Pass a base URL** when the analysis runs (`--base-url https://dam.hf.uio.no/…/20162/analysis`), so IIIF ids and `contentUrl`s are real.
3. **On the catalog page:** add `<track kind="chapters" src="…/chapters.vtt">` to the video element; embed `schemaorg.json` in the page head; either mount `segments-player.js` on the video element with `segments.json`, or point a IIIF A/V viewer (Clover, Ramp, Mirador with the A/V plugin) at `manifest.json`. Both work today.
4. **Editing:** expose `curated.json` fields (title, people, licence, privacy level, rights per work, speaker names) in the DAM's edit form. The file is the contract; the analysis reads it and never writes it.
5. **Deposit:** hand the bag to the repository, or its `export/ebucore.xml` if the repository wants a record only.

## What stays open

- Person identifiers: we record names; adding ORCID/UiO ids to `curated.json` people is a form field away.
- Rights status per work is a human judgement; the analysis only pre-fills work and composer from the programme.
- `ebucore.xml` validates against the official EBUCore XSD (from EBU's GitHub, with the Dublin Core import resolved locally); both test recordings pass. `premis.xml` is well-formed and follows PREMIS 3; the Library of Congress blocks automated schema download, so vendor `premis.xsd` into `~/.cache/av-xsd` once to validate it too.
- The record schema is versioned (`urn:avsegmenter:record:1.0`); changes are additive.
- The library carries no UiO specifics: organisation, provider URL, identifiers and namespace come from `curated.json` and the command line, so the same package serves another department or institution.

*Command:* `avsegmenter VIDEO -o OUT [--profile concert|talk] [--programme plan.docx|json] [--metadata curated.json] [--base-url URL] [--identifier URN] [--bag]`
