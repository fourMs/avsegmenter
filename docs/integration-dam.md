# Integrating avsegmenter with a catalog (the UiO DAM case)

avsegmenter is independent of any catalog. This page records how it attaches to one concrete
system, the University of Oslo's DAM (`dam.hf.uio.no`, a Next.js app that renders a plain HTML5
`<video>` with a signed media URL), so that another catalog can copy the pattern.

## What the catalog stores

One analysis folder per asset, next to the media (for asset `imv/20162`:
`collections/imv/20162/analysis/`), served as static files. It contains `segments.json`,
`curated.json`, `player.html`, `chapters.vtt`, `thumbs/`, `videogram.png` and `export/` with the
standard metadata (see `metadata-approach.md`). Nothing in it is large.

## Running the analysis

On the server that has the media, once per upload (GPU recommended):

```bash
avsegmenter /media/collections/imv/20162/recording.mp4 \
    -o /media/collections/imv/20162/analysis \
    --base-url https://dam.hf.uio.no/media/collections/imv/20162/analysis \
    --identifier urn:uio:dam:imv:20162 \
    --programme kjoreplan.docx --metadata curated.json
```

`--base-url` makes the IIIF ids and `contentUrl`s real; `--identifier` is the persistent id the
catalog uses. Re-running after edits to `curated.json` takes about a minute (everything else is cached).

## On the catalog page

Three levels, any of which works on its own:

1. Chapters only: add `<track kind="chapters" src="…/analysis/chapters.vtt" srclang="no" default>`
   to the video element.
2. Timeline component: load `segments-player.js` and call
   `SegmentsPlayer.mount({ video, url: '…/analysis/segments.json', container, assetBase: '…/analysis/' })`
   in the client component that owns the video. It draws the strips, the detail panel and the metadata
   box under the player and follows the playhead. In a Next.js client component:

   ```tsx
   useEffect(() => {
     const s = document.createElement('script'); s.src = '/js/segments-player.js';
     s.onload = () => (window as any).SegmentsPlayer.mount({ video: videoRef.current, url: `${base}/segments.json`, container: boxRef.current, assetBase: `${base}/` });
     document.body.appendChild(s);
   }, []);
   ```
3. IIIF viewer: point a IIIF audio/video viewer (Clover, Ramp, Mirador with the A/V plugin) at
   `…/analysis/export/manifest.json`; the parts and pieces appear as its table of contents.

Also embed `export/schemaorg.json` in the page head for discovery.

## Editing

`curated.json` is the contract between the catalog's edit form and the analysis: title, description,
people with roles, licence, privacy level and note, per-work rights status, speaker names, access and
embargo. The analysis reads it and never writes it. Field list: `record-schema.md`.

## Deposit

`--bag` writes a BagIt bag with the media hard-linked; hand it to the repository, or hand over
`export/ebucore.xml` alone where the repository wants a record rather than a package.

## Notes from the UiO deployment

- The DAM's signed media URLs (`/api/public/media?id=…`) redirect to S3 with a five-minute signature;
  the player component only needs the `<video>` element and does not care where the media comes from.
- Uploaders' names appear in the asset record (`uploader`), not in the analysis; do not copy them into
  `curated.json` people unless they are contributors.
