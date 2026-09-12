"""schema.org JSON-LD for the catalog page: a VideoObject that records an Event, with Clips."""
from __future__ import annotations


def schemaorg_jsonld(rec: dict) -> dict:
    d, t, s, r = rec["descriptive"], rec["technical"], rec["structural"], rec["rights"]
    base = (rec.get("base_url") or "").rstrip("/")
    clips = [{"@type": "Clip", "name": it.get("title") or f"{it['kind']} {it.get('index')}", "startOffset": it["start"], "endOffset": it["end"],
              **({"actor": [{"@type": "Person", "name": n.strip()} for n in (it.get("plan") or {}).get("performers", "").split(",") if n.strip()]} if (it.get("plan") or {}).get("performers") else {})}
             for it in s["items"] if it.get("kind") != "break"]
    event_type = "MusicEvent" if d.get("event_type") == "concert" else "EducationEvent"
    people = [{"@type": "Person", "name": p["name"], "roleName": p.get("role")} for p in d.get("people", [])]
    obj = {
        "@context": "https://schema.org", "@type": "VideoObject", "@id": rec["identifier"],
        "name": d["title"], "description": d.get("description"), "dateCreated": d.get("date"),
        "duration": f"PT{int(t['duration_s'] // 60)}M{int(t['duration_s'] % 60)}S",
        "encodingFormat": "video/mp4", "width": t.get("width"), "height": t.get("height"),
        "contentUrl": f"{base}/{t.get('file')}" if base else None, "sha256": t.get("sha256"),
        "inLanguage": d.get("language"), "genre": d.get("genre"), "keywords": ", ".join(d.get("keywords", [])) or None,
        "license": r.get("license_url") or r.get("license"), "copyrightHolder": {"@type": "Organization", "name": r["rights_holder"]} if r.get("rights_holder") else None,
        "conditionsOfAccess": f"{r.get('access')}; privacy level {((r.get('privacy') or {}).get('level'))}",
        "publisher": {"@type": "Organization", "name": d.get("organisation")},
        "recordedAt": {"@type": event_type, "name": d["title"], "startDate": d.get("date"), "location": {"@type": "Place", "name": d.get("venue")} if d.get("venue") else None, "performer": people or None},
        "hasPart": clips,
        "provider": {"@type": "SoftwareApplication", "name": "concert-segmenter", "softwareVersion": next((x.get("version") for x in rec["provenance"]["software"] if x["name"] == "concert-segmenter"), None)},
    }
    return _clean(obj)


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items() if v is not None and v != [] and v != {}}
    if isinstance(x, list):
        return [_clean(v) for v in x if v is not None]
    return x
