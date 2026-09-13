"""IIIF Presentation 3 manifest and W3C Web Annotations from the record.

The manifest has one Canvas with the recording's duration, a painting annotation pointing at the
video (``base_url``), ``structures`` (Ranges) for the pieces or parts, and annotation pages for the
segments, speaker turns and camera cuts targeted by media fragments (``#t=start,end``). Any IIIF
audio/video viewer shows the ranges as a table of contents; the annotation pages are also valid
Web Annotation collections on their own.
"""
from __future__ import annotations

CTX = "http://iiif.io/api/presentation/3/context.json"
WA_CTX = "http://www.w3.org/ns/anno.jsonld"


def _lang(rec, text):
    return {(rec["descriptive"].get("language") or "none"): [str(text)]}


def iiif_manifest(rec: dict) -> dict:
    base = (rec.get("base_url") or "https://example.org/recordings/" + rec["identifier"].split(":")[-1]).rstrip("/")
    dur = float(rec["technical"]["duration_s"])
    tech = rec["technical"]
    canvas_id = f"{base}/canvas/1"
    video_url = f"{base}/{tech.get('file')}"
    def rng(it, children=None):
        r = {"id": f"{base}/range/{it['kind']}-{it.get('index')}", "type": "Range", "label": _lang(rec, it.get("title") or f"{it['kind']} {it.get('index')}"),
             "items": [{"id": f"{canvas_id}#t={it['start']},{it['end']}", "type": "Canvas"}]}
        if children:
            r["items"] = children + r["items"]
        return r
    all_items = rec["structural"]["items"]
    parts = [it for it in all_items if it.get("kind") == "part"]
    pieces = [it for it in all_items if it.get("kind") == "piece"]
    if len(parts) > 1:
        ranges = [rng(pt, [rng(pc) for pc in pieces if pc.get("part_index") == pt.get("index")]) for pt in parts]
    else:
        ranges = [rng(pc) for pc in pieces] or [rng(pt) for pt in parts]
    def page(name, annos):
        return {"id": f"{base}/annotations/{name}", "type": "AnnotationPage", "items": annos}
    seg_annos = [{"id": f"{base}/annotation/{s['id']}", "type": "Annotation", "motivation": "tagging",
                  "body": [{"type": "TextualBody", "value": s["kind"], "purpose": "tagging"},
                           *([{"type": "SpecificResource", "source": s["audioset"]["uri"], "purpose": "classifying"}] if (s.get("audioset") or {}).get("uri") else []),
                           *([{"type": "TextualBody", "value": s["transcript"], "purpose": "transcribing"}] if s.get("transcript") else [])],
                  "target": f"{canvas_id}#t={s['start']},{s['end']}", "confidence": s.get("confidence")} for s in rec["structural"]["segments"]]
    turn_annos = [{"id": f"{base}/annotation/turn-{k:04d}", "type": "Annotation", "motivation": "commenting",
                   "body": [{"type": "TextualBody", "value": (rec["structural"]["speakers"].get(t["speaker"]) or {}).get("name") or t["speaker"], "purpose": "tagging"},
                            *([{"type": "TextualBody", "value": t["text"], "purpose": "transcribing"}] if t.get("text") else [])],
                   "target": f"{canvas_id}#t={t['start']},{t['end']}"} for k, t in enumerate(rec["structural"]["turns"])]
    cam = rec["structural"].get("camera") or {}
    cut_annos = [{"id": f"{base}/annotation/cut-{k:03d}", "type": "Annotation", "motivation": "tagging",
                  "body": {"type": "TextualBody", "value": "camera cut", "purpose": "tagging"}, "target": f"{canvas_id}#t={c}"} for k, c in enumerate(cam.get("cuts") or [])]
    annos = [page("segments", seg_annos)]
    if turn_annos: annos.append(page("speaker-turns", turn_annos))
    if cut_annos: annos.append(page("camera-cuts", cut_annos))
    builtin = {"segments", "pieces", "parts", "turns", "cuts"}
    for tier in (rec.get("research") or {}).get("tiers", []):
        if tier["id"] in builtin:
            continue
        annos.append(page(f"tier-{tier['id']}", [
            {"id": f"{base}/annotation/{tier['id']}-{k:04d}", "type": "Annotation", "motivation": "commenting" if tier.get("source", "").startswith(("ELAN", "elan")) else "tagging",
             "body": {"type": "TextualBody", "value": it.get("label") or tier["label"], "purpose": "tagging"},
             "target": f"{canvas_id}#t={it['start']}" + (f",{it['end']}" if it.get("end", it["start"]) > it["start"] else "")}
            for k, it in enumerate(tier.get("items", []))]))
    rights = rec["rights"]
    manifest = {
        "@context": CTX, "id": f"{base}/manifest.json", "type": "Manifest",
        "label": _lang(rec, rec["descriptive"]["title"]),
        "summary": _lang(rec, rec["descriptive"].get("description") or rec["descriptive"]["title"]),
        "metadata": [{"label": _lang(rec, k), "value": _lang(rec, v)} for k, v in (
            ("Date", rec["descriptive"].get("date")), ("Venue", rec["descriptive"].get("venue")), ("Organisation", rec["descriptive"].get("organisation")),
            ("Event type", rec["descriptive"].get("event_type")), ("People", "; ".join(f"{p['name']} ({p['role']})" for p in rec["descriptive"].get("people", []))),
            ("Privacy level", (rights.get("privacy") or {}).get("level")), ("Access", rights.get("access"))) if v],
        "requiredStatement": {"label": _lang(rec, "Rights"), "value": _lang(rec, (rights.get("license") or "not stated") + (f" – {rights['rights_holder']}" if rights.get("rights_holder") else ""))},
        **({"rights": rights["license_url"]} if rights.get("license_url") else {}),
        **({"provider": [{"id": rec["descriptive"].get("organisation_url") or f"{base}/organisation", "type": "Agent", "label": _lang(rec, rec["descriptive"]["organisation"])}]} if rec["descriptive"].get("organisation") else {}),
        "items": [{"id": canvas_id, "type": "Canvas", "duration": dur, **({"width": tech["width"], "height": tech["height"]} if tech.get("width") else {}),
                   "label": _lang(rec, "Recording"),
                   "items": [{"id": f"{canvas_id}/page/1", "type": "AnnotationPage", "items": [
                       {"id": f"{canvas_id}/page/1/anno/1", "type": "Annotation", "motivation": "painting",
                        "body": {"id": video_url, "type": "Video", "format": "video/mp4", "duration": dur, **({"width": tech["width"], "height": tech["height"]} if tech.get("width") else {})},
                        "target": canvas_id}]}],
                   "annotations": annos}],
        "structures": ranges,
        "seeAlso": [{"id": f"{base}/ebucore.xml", "type": "Dataset", "format": "application/xml", "profile": "urn:ebu:metadata-schema:ebucore", "label": _lang(rec, "EBUCore record")},
                    {"id": f"{base}/segments.json", "type": "Dataset", "format": "application/json", "label": _lang(rec, "Analysis (segments.json)")}]
                   + [{"id": f"{base}/tracks/{t['id']}.csv", "type": "Dataset", "format": "text/csv", "label": _lang(rec, t.get("label") or t["id"])}
                      for t in (rec.get("research") or {}).get("tracks", []) if t.get("kind") == "curve"],
    }
    return manifest


def web_annotations(rec: dict) -> dict:
    """The same annotations as one W3C AnnotationCollection (for tools that are not IIIF viewers)."""
    m = iiif_manifest(rec)
    pages = m["items"][0]["annotations"]
    return {"@context": WA_CTX, "id": m["id"].replace("manifest.json", "annotations.json"), "type": "AnnotationCollection",
            "label": rec["descriptive"]["title"], "total": sum(len(p["items"]) for p in pages),
            "first": {"id": pages[0]["id"], "type": "AnnotationPage", "items": [a for p in pages for a in p["items"]]}}
