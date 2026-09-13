"""JAMS (JSON Annotated Music Specification) view of the tiers: what the MIR community exchanges."""
from __future__ import annotations

NS = {"segments": "segment_open", "pieces": "segment_open", "parts": "segment_open", "turns": "tag_open", "cuts": "tag_open",
      "novelty": "onset", "cues": "tag_open"}


def jams_doc(rec: dict) -> dict:
    tech, desc = rec["technical"], rec["descriptive"]
    annotations = []
    for tier in (rec.get("research") or {}).get("tiers", []):
        ns = NS.get(tier["id"], "tag_open" if tier.get("kind") == "point" else "segment_open")
        data = []
        for it in tier.get("items", []):
            dur = max(0.0, float(it.get("end", it["start"])) - float(it["start"]))
            data.append({"time": float(it["start"]), "duration": dur if ns != "onset" else 0.0,
                         "value": it.get("label") or tier["label"], "confidence": it.get("confidence")})
        annotations.append({"namespace": ns, "data": data,
                            "annotation_metadata": {"curator": {"name": "", "email": ""}, "annotator": {"tool": tier.get("source") or "avsegmenter"},
                                                    "version": "", "corpus": desc.get("organisation") or "", "annotation_tools": tier.get("source") or "avsegmenter",
                                                    "annotation_rules": "", "validation": "", "data_source": "automatic" if not tier.get("author") else "manual"},
                            "sandbox": {"tier_id": tier["id"], "tier_label": tier["label"], "kind": tier.get("kind")}})
    return {"file_metadata": {"title": desc.get("title") or "", "artist": ", ".join(p["name"] for p in desc.get("people", [])[:6]),
                              "release": "", "duration": float(tech.get("duration_s") or 0), "identifiers": {"local": rec["identifier"]},
                              "jams_version": "0.3.4"},
            "annotations": annotations, "sandbox": {"generator": "avsegmenter", "record_schema": rec.get("schema")}}
