"""EBUCore 1.10 XML from the record: the master archival document.

One ``ebuCoreMain`` with ``coreMetadata``: identifiers, title, description, date, type (genre and the
event type), contributors with roles, coverage (venue), rights, format (technical), and one
``part`` per structural item (pieces or parts), each with start time and duration. Segments and
speaker turns go into ``part`` elements of their own type so that a MAM that only reads parts still
sees the applause and the talk. Provenance travels in ``description`` with type "provenance" and in
the format's ``technicalAttribute`` elements; the full PREMIS goes alongside (see :mod:`provenance`).
"""
from __future__ import annotations
from xml.etree import ElementTree as ET

EBU = "urn:ebu:metadata-schema:ebucore"
DC = "http://purl.org/dc/elements/1.1/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "urn:ebu:metadata-schema:ebucore https://raw.githubusercontent.com/ebu/ebucore/master/EBUCore.xsd"
ET.register_namespace("ebucore", EBU); ET.register_namespace("dc", DC); ET.register_namespace("xsi", XSI)


def _e(parent, tag, text=None, ns=EBU, **attrs):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}", {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = str(text)
    return el


def _tc(seconds: float) -> str:
    """xs:time-like normalPlayTime ``HH:MM:SS.mmm``."""
    s = float(seconds); h = int(s // 3600); m = int(s % 3600 // 60); sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def _dur(seconds: float) -> str:
    """xs:duration ``PT#H#M#S``."""
    s = float(seconds); h = int(s // 3600); m = int(s % 3600 // 60); sec = round(s % 60, 3)
    return f"PT{h}H{m}M{sec}S"


def _part(parent, part_id, ptype, title, start, end, extra: dict | None = None, description=None):
    """One ``part`` in coreMetadataType order: title, description(s), partStartTime, partDuration."""
    p = _e(parent, "part", partId=part_id, partName=title, typeLabel=ptype)
    _e(_e(p, "title"), "title", title, ns=DC)
    if description:
        _e(_e(p, "description", typeLabel="programme"), "description", description, ns=DC)
    for k, v in (extra or {}).items():
        if v is not None:
            _e(_e(p, "description", typeLabel=k), "description", v, ns=DC)
    _e(_e(p, "partStartTime"), "normalPlayTime", _tc(start))          # timeType: HH:MM:SS.mmm
    _e(_e(p, "partDuration"), "normalPlayTime", _dur(max(0.0, end - start)))   # durationType: PT#H#M#S
    return p


def ebucore_xml(rec: dict) -> bytes:
    desc, tech, struct, rights, prov = rec["descriptive"], rec["technical"], rec["structural"], rec["rights"], rec["provenance"]
    root = ET.Element(f"{{{EBU}}}ebuCoreMain", {f"{{{XSI}}}schemaLocation": SCHEMA_LOCATION, "version": "1.10",
                                                 "dateLastModified": (prov.get("record_built") or "")[:10],
                                                 "documentId": rec["identifier"]})
    core = _e(root, "coreMetadata")
    from .vocab import role_term
    _e(_e(core, "title", typeLabel="main"), "title", desc.get("title"), ns=DC)
    for kw in desc.get("keywords", []):
        _e(_e(core, "subject"), "subject", kw, ns=DC)
    if desc.get("description"):
        _e(_e(core, "description", typeLabel="summary"), "description", desc["description"], ns=DC)
    _e(_e(core, "description", typeLabel="provenance"), "description",
       "Automatic segmentation by " + "; ".join(f"{s['name']} {s.get('version')}" for s in prov["software"] if s.get("version"))
       + ". Curated fields: " + (", ".join(prov.get("curated_fields") or []) or "none") + ".", ns=DC)
    if desc.get("organisation"):
        pub = _e(core, "publisher"); _e(_e(pub, "organisationDetails"), "organisationName", desc["organisation"])
    for p in desc.get("people", []):
        c = _e(core, "contributor")
        cd = _e(c, "contactDetails"); _e(cd, "name", p["name"])
        if p.get("affiliation"):
            _e(_e(c, "organisationDetails"), "organisationName", p["affiliation"])
        rt = role_term(p.get("role", ""))
        _e(c, "role", None, typeLabel=rt["label"], typeDefinition=rt["scheme"])
    if desc.get("date"):
        _e(_e(core, "date"), "created", None, startDate=desc["date"])
    t = _e(core, "type")
    _e(t, "genre", None, typeLabel=desc.get("genre"), typeDefinition="http://www.ebu.ch/metadata/cs/ebu_ContentGenreCS.xml")
    _e(t, "objectType", None, typeLabel="Recording of event", typeDefinition=f"{rec.get('urn_prefix', 'urn:avsegmenter')}:event-type:{desc.get('event_type')}")

    # technical
    f = _e(core, "format", formatId="original")
    if tech.get("container"):
        _e(f, "containerFormat", None, containerFormatName=tech["container"])
    vf = _e(f, "videoFormat", videoFormatName=tech.get("video_codec"))
    if tech.get("width"): _e(vf, "width", tech["width"], unit="pixel")
    if tech.get("height"): _e(vf, "height", tech["height"], unit="pixel")
    if tech.get("fps"):
        fps = float(tech["fps"])
        if abs(fps - round(fps)) < 1e-3:
            _e(vf, "frameRate", int(round(fps)))
        else:  # 29.97 = 30 * 1000/1001 and friends
            _e(vf, "frameRate", int(round(fps * 1001 / 1000)), factorNumerator="1000", factorDenominator="1001")
    if tech.get("video_bitrate_kbps"): _e(vf, "bitRate", int(tech["video_bitrate_kbps"] * 1000))
    for k in ("pix_fmt", "bit_depth", "color", "profile"):
        if tech.get(k): _e(vf, "technicalAttributeString", tech[k], typeLabel=k)
    af = _e(f, "audioFormat", audioFormatName=tech.get("audio_codec"))
    if tech.get("sample_rate_hz"): _e(af, "samplingRate", tech["sample_rate_hz"])
    if tech.get("audio_bit_depth"): _e(af, "sampleSize", tech["audio_bit_depth"])
    if tech.get("audio_bitrate_kbps"): _e(af, "bitRate", int(tech["audio_bitrate_kbps"] * 1000))
    if tech.get("channels"): _e(af, "technicalAttributeString", tech.get("channel_layout") or f"{tech['channels']} channels", typeLabel="channels")
    lo = (rec.get("quality") or {}).get("loudness") or {}
    for key, label in (("integrated_lufs", "EBU R128 integrated loudness LUFS"), ("loudness_range_lu", "EBU R128 loudness range LU"), ("true_peak_dbtp", "EBU R128 true peak dBTP")):
        if lo.get(key) is not None:
            _e(af, "technicalAttributeString", lo[key], typeLabel=label)
    if tech.get("size_bytes"): _e(f, "fileSize", tech["size_bytes"])
    _e(f, "fileName", tech.get("file"))
    if tech.get("duration_s"): _e(_e(f, "duration"), "normalPlayTime", _dur(tech["duration_s"]))
    if tech.get("sha256"):
        h = _e(f, "hash"); _e(h, "hashValue", tech["sha256"]); _e(h, "hashFunction", None, typeLabel="SHA-256")

    qc = (rec.get("quality") or {}).get("qc") or {}
    for it in qc.get("items", []):
        _e(f, "technicalAttributeString", f"{it['outcome']}" + (f" ({it.get('count')})" if it.get("count") is not None else ""), typeLabel=f"QC {it['id']}")
    _e(_e(core, "identifier", typeLabel="local"), "identifier", rec["identifier"], ns=DC)
    if desc.get("language"):
        _e(_e(core, "language", typeLabel="main"), "language", desc["language"], ns=DC)
    if desc.get("venue"):
        _e(_e(_e(core, "coverage"), "spatial"), "location", desc["venue"])

    # rights
    r = _e(core, "rights", typeLabel="licence")
    _e(r, "rights", rights.get("license") or "not stated", ns=DC)
    if rights.get("license_url"):
        _e(r, "rightsLink", rights["license_url"])
    if rights.get("rights_holder"):
        _e(_e(_e(r, "rightsHolder"), "organisationDetails"), "organisationName", rights["rights_holder"])
    priv = rights.get("privacy") or {}
    a = _e(core, "rights", typeLabel="access")
    _e(a, "rights", f"access: {rights.get('access')}; privacy level: {priv.get('level', 'not set')}"
       + (f" ({priv.get('note')})" if priv.get("note") else "") + (f"; embargo until {rights['embargo_until']}" if rights.get("embargo_until") else ""), ns=DC)
    for w in rights.get("works") or []:
        wr = _e(core, "rights", typeLabel="work")
        _e(wr, "rights", " – ".join(x for x in (w.get("work"), w.get("composer")) if x) + f": {w.get('status', 'unknown')}" + (f" ({w['note']})" if w.get("note") else ""), ns=DC)

    # structure
    for it in struct.get("items", []):
        if it.get("kind") == "break":
            continue
        ptype = "piece" if it["kind"] == "piece" else "part"
        extra = {}
        if it.get("people_on_stage") is not None: extra["people_on_stage"] = it["people_on_stage"]
        if it.get("performers") and it["performers"].get("estimate") is not None: extra["people_on_stage"] = it["performers"]["estimate"]
        if it.get("instruments"): extra["instruments"] = ", ".join(i["label"] for i in it["instruments"][:4])
        if it.get("genres"): extra["genre_tags"] = ", ".join(g["label"] for g in it["genres"][:3])
        if it.get("speakers"): extra["floor"] = ", ".join(f"{k} {v:.0%}" for k, v in list(it["speakers"].items())[:3])
        pl = it.get("plan") or {}
        descr = " · ".join(x for x in (pl.get("work"), pl.get("composer"), pl.get("performers")) if x) or None
        _part(core, f"{ptype}-{it.get('index')}", ptype, it.get("title") or f"{ptype} {it.get('index')}", it["start"], it["end"], extra, descr)
    for s in struct.get("segments", []):
        extra = {"confidence": s.get("confidence"), "audioset": (s.get("audioset") or {}).get("id")}
        _part(core, s["id"], f"segment:{s['kind']}", s.get("title") or s["kind"], s["start"], s["end"], extra)
    for k, t in enumerate(struct.get("turns", [])):
        name = (struct.get("speakers", {}).get(t["speaker"]) or {}).get("name") or t["speaker"]
        _part(core, f"turn-{k:04d}", "speaker-turn", name, t["start"], t["end"], {"speaker": t["speaker"]}, (t.get("text") or None))
    cam = struct.get("camera") or {}
    for k, c in enumerate(cam.get("cuts") or []):
        _part(core, f"cut-{k:03d}", "camera-cut", "cut", c, c, {"mpeg7": "cut"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
