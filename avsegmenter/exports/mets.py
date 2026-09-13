"""A METS wrapper for the bag: descriptive (EBUCore), technical (ffprobe facts, loudness, QC), preservation
(PREMIS) metadata and a file section over the payload, with a structural map of parts and pieces as timed divs.
"""
from __future__ import annotations
import datetime as _dt
from xml.etree import ElementTree as ET

METS = "http://www.loc.gov/METS/"
XLINK = "http://www.w3.org/1999/xlink"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
for p, u in (("mets", METS), ("xlink", XLINK), ("xsi", XSI)):
    ET.register_namespace(p, u)


def _e(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, f"{{{METS}}}{tag}", {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = str(text)
    return el


def _tc(s: float) -> str:
    s = float(s); return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def mets_xml(rec: dict, files: list[dict], ebucore_ref: str = "export/ebucore.xml", premis_ref: str = "export/premis.xml") -> bytes:
    """``files``: [{"id", "path", "mimetype", "size", "sha256", "use"}] relative to the bag's data/."""
    now = _dt.datetime.now().isoformat(timespec="seconds")
    root = ET.Element(f"{{{METS}}}mets", {"OBJID": rec["identifier"], "LABEL": rec["descriptive"].get("title") or "",
                                            "TYPE": "audio-video recording",
                                            f"{{{XSI}}}schemaLocation": f"{METS} http://www.loc.gov/standards/mets/mets.xsd"})
    hdr = _e(root, "metsHdr", CREATEDATE=now, RECORDSTATUS="COMPLETE")
    ag = _e(hdr, "agent", ROLE="CREATOR", TYPE="OTHER", OTHERTYPE="SOFTWARE"); _e(ag, "name", "avsegmenter " + str(next((s.get("version") for s in rec["provenance"]["software"] if s["name"] == "avsegmenter"), "")))
    if rec["descriptive"].get("organisation"):
        ag2 = _e(hdr, "agent", ROLE="CUSTODIAN", TYPE="ORGANIZATION"); _e(ag2, "name", rec["descriptive"]["organisation"])
    dmd = _e(root, "dmdSec", ID="dmd-ebucore")
    _e(dmd, "mdRef", LOCTYPE="URL", MDTYPE="OTHER", OTHERMDTYPE="EBUCore", MIMETYPE="application/xml", **{f"{{{XLINK}}}href": ebucore_ref})
    amd = _e(root, "amdSec", ID="amd")
    tech = _e(amd, "techMD", ID="tech-ebucore")
    _e(tech, "mdRef", LOCTYPE="URL", MDTYPE="OTHER", OTHERMDTYPE="EBUCore", MIMETYPE="application/xml", **{f"{{{XLINK}}}href": ebucore_ref})
    q = rec.get("quality") or {}
    if q.get("loudness") or q.get("qc"):
        t2 = _e(amd, "techMD", ID="tech-quality"); w = _e(t2, "mdWrap", MDTYPE="OTHER", OTHERMDTYPE="avsegmenter-quality", MIMETYPE="text/xml")
        x = _e(w, "xmlData")
        lo = (q.get("loudness") or {})
        el = ET.SubElement(x, "loudness", {"standard": lo.get("standard", "EBU R128")})
        for k in ("integrated_lufs", "loudness_range_lu", "true_peak_dbtp"):
            if lo.get(k) is not None:
                ET.SubElement(el, k).text = str(lo[k])
        qc = ET.SubElement(x, "qualityControl", {"standard": (q.get("qc") or {}).get("standard", "")})
        for it in (q.get("qc") or {}).get("items", []):
            ET.SubElement(qc, "item", {"id": it["id"], "outcome": it["outcome"], "count": str(it.get("count", ""))}).text = it.get("label")
    rights = _e(amd, "rightsMD", ID="rights"); rw = _e(rights, "mdWrap", MDTYPE="OTHER", OTHERMDTYPE="avsegmenter-rights", MIMETYPE="text/xml"); rx = _e(rw, "xmlData")
    r = rec["rights"]; ET.SubElement(rx, "rights", {"license": r.get("license") or "", "access": r.get("access") or "", "privacy": ((r.get("privacy") or {}).get("level") or "")})
    dp = _e(amd, "digiprovMD", ID="prov-premis")
    _e(dp, "mdRef", LOCTYPE="URL", MDTYPE="PREMIS", MIMETYPE="application/xml", **{f"{{{XLINK}}}href": premis_ref})
    fsec = _e(root, "fileSec")
    groups: dict[str, ET.Element] = {}
    for f in files:
        use = f.get("use", "derivative")
        grp = groups.get(use) or _e(fsec, "fileGrp", USE=use); groups[use] = grp
        fe = _e(grp, "file", ID=f["id"], MIMETYPE=f.get("mimetype"), SIZE=f.get("size"), CHECKSUMTYPE="SHA-256" if f.get("sha256") else None, CHECKSUM=f.get("sha256"))
        _e(fe, "FLocat", LOCTYPE="URL", **{f"{{{XLINK}}}href": f["path"]})
    smap = _e(root, "structMap", TYPE="logical", LABEL="Parts and pieces")
    top = _e(smap, "div", TYPE="recording", LABEL=rec["descriptive"].get("title") or "", DMDID="dmd-ebucore", ADMID="amd")
    master = next((f for f in files if f.get("use") == "master"), None)
    items = rec["structural"]["items"]
    parts = [i for i in items if i.get("kind") == "part"]; pieces = [i for i in items if i.get("kind") == "piece"]
    def timed(parent, it, typ):
        d = _e(parent, "div", TYPE=typ, LABEL=it.get("title") or f"{typ} {it.get('index')}", ORDER=it.get("index"))
        if master:
            fp = _e(d, "fptr"); _e(fp, "area", FILEID=master["id"], BETYPE="TIME", BEGIN=_tc(it["start"]), END=_tc(it["end"]))
        return d
    if parts:
        for pt in parts:
            d = timed(top, pt, "part")
            for pc in pieces:
                if pc.get("part_index") == pt.get("index"):
                    timed(d, pc, "piece")
    else:
        for pc in pieces:
            timed(top, pc, "piece")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
