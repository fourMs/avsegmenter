"""PREMIS 3 events: what produced each layer of the record, with which software, models and parameters."""
from __future__ import annotations
import json
from xml.etree import ElementTree as ET

PREMIS = "http://www.loc.gov/premis/v3"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("premis", PREMIS); ET.register_namespace("xsi", XSI)


def _e(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, f"{{{PREMIS}}}{tag}", attrs)
    if text is not None:
        el.text = str(text)
    return el


def premis_xml(rec: dict) -> bytes:
    prov, tech = rec["provenance"], rec["technical"]
    root = ET.Element(f"{{{PREMIS}}}premis", {"version": "3.0", f"{{{XSI}}}schemaLocation": f"{PREMIS} https://www.loc.gov/standards/premis/v3/premis.xsd"})
    # the object
    obj = _e(root, "object", {f"{{{XSI}}}type": "premis:file"})
    oi = _e(obj, "objectIdentifier"); _e(oi, "objectIdentifierType", "URI"); _e(oi, "objectIdentifierValue", rec["identifier"])
    oc = _e(obj, "objectCharacteristics")
    if tech.get("sha256"):
        fx = _e(oc, "fixity"); _e(fx, "messageDigestAlgorithm", "SHA-256"); _e(fx, "messageDigest", tech["sha256"])
    if tech.get("size_bytes"):
        _e(oc, "size", tech["size_bytes"])
    fm = _e(oc, "format"); fd = _e(fm, "formatDesignation"); _e(fd, "formatName", tech.get("container") or "video")
    if tech.get("video_codec"):
        _e(fd, "formatVersion", f"{tech.get('video_codec')} / {tech.get('audio_codec')}")
    # agents
    agents = []
    for s in prov["software"]:
        if s.get("version"):
            agents.append((f"software:{s['name']}", s["name"], s["version"], "software"))
    for m in prov.get("models", []):
        agents.append((f"model:{m['name']}", m["name"], m.get("use"), "model"))
    for aid, name, ver, kind in agents:
        a = _e(root, "agent"); ai = _e(a, "agentIdentifier"); _e(ai, "agentIdentifierType", "local"); _e(ai, "agentIdentifierValue", aid)
        _e(a, "agentName", name); _e(a, "agentType", kind)
        if ver:
            _e(a, "agentVersion" if kind == "software" else "agentNote", ver)
    # events: one per layer
    def event(eid, etype, when, detail, outcome="success", agent_ids=()):
        ev = _e(root, "event"); ei = _e(ev, "eventIdentifier"); _e(ei, "eventIdentifierType", "local"); _e(ei, "eventIdentifierValue", eid)
        _e(ev, "eventType", etype); _e(ev, "eventDateTime", when or "")
        di = _e(ev, "eventDetailInformation"); _e(di, "eventDetail", detail)
        oi = _e(ev, "eventOutcomeInformation"); _e(oi, "eventOutcome", outcome)
        for a in agent_ids:
            la = _e(ev, "linkingAgentIdentifier"); _e(la, "linkingAgentIdentifierType", "local"); _e(la, "linkingAgentIdentifierValue", a)
        lo = _e(ev, "linkingObjectIdentifier"); _e(lo, "linkingObjectIdentifierType", "URI"); _e(lo, "linkingObjectIdentifierValue", rec["identifier"])
        return ev
    sw = [f"software:{s['name']}" for s in prov["software"] if s.get("version")]
    event("analysis-structural", "metadata extraction", prov.get("generated"),
          "Segmentation into music/speech/applause/silence, pieces or parts, speaker turns, camera cuts. Parameters: " + json.dumps(prov.get("parameters") or {}),
          agent_ids=sw + [f"model:{m['name']}" for m in prov.get("models", [])])
    event("analysis-technical", "format identification", prov.get("generated"), "ffprobe container/stream facts and SHA-256 of the file", agent_ids=sw[:1])
    qc = (rec.get("quality") or {}).get("qc") or {}
    if qc.get("items"):
        bad = [i for i in qc["items"] if i["outcome"] == "warning"]
        event("quality-control", "quality control", prov.get("generated"),
              "; ".join(f"{i['id']}: {i['outcome']}" + (f" ({i.get('count')})" if i.get("count") is not None else "") for i in qc["items"]) + f". Loudness: {json.dumps((rec.get('quality') or {}).get('loudness') and {k: v for k, v in rec['quality']['loudness'].items() if k != 'momentary_lufs_1hz'})}",
              outcome="pass with warnings" if bad else "pass", agent_ids=sw[:1])
    for k, der in enumerate(rec.get("derivatives") or []):
        event(f"derivation-{k:02d}", "creation", prov.get("generated"), f"{der.get('role')}: {der['path']} ({der.get('mimetype')}) by {der.get('generator')}" + (f", SHA-256 {der['sha256']}" if der.get("sha256") else ""), agent_ids=sw[:1])
    event("record-built", "creation", prov.get("record_built"), "Canonical record built; curated fields merged over automatic values: " + (", ".join(prov.get("curated_fields") or []) or "none"), agent_ids=sw[:1])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
