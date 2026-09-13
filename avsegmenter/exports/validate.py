"""Checks: well-formed XML, EBUCore/PREMIS schema validation when the XSDs are available, IIIF and
JSON-LD shape checks, BagIt manifest integrity. Returns a list of findings; empty means clean."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

XSD_DIRS = [Path(os.environ.get("AV_XSD_DIR", "")), Path.home() / ".cache" / "av-xsd"]


def _xsd(name: str) -> Path | None:
    for d in XSD_DIRS:
        if d and (d / name).exists():
            return d / name
    return None


def _parser_with_local_imports():
    """An XML parser whose resolver serves the schemas EBUCore imports by URL (xml.xsd, simpledc) from
    the local XSD directory, so validation works offline."""
    from lxml import etree

    class _Local(etree.Resolver):
        def resolve(self, url, pubid, context):
            name = url.rsplit("/", 1)[-1]
            local = _xsd(name)
            return self.resolve_filename(str(local), context) if local else None

    parser = etree.XMLParser()
    parser.resolvers.add(_Local())
    return parser


def validate_xml(path: Path, xsd_name: str | None = None) -> list[str]:
    out = []
    try:
        from lxml import etree
        doc = etree.parse(str(path))
    except Exception as e:  # noqa: BLE001
        return [f"{path.name}: not well-formed: {e}"]
    xsd = _xsd(xsd_name) if xsd_name else None
    if xsd:
        try:
            schema = etree.XMLSchema(etree.parse(str(xsd), _parser_with_local_imports()))
            if not schema.validate(doc):
                out += [f"{path.name}: {e.line}: {e.message}" for e in list(schema.error_log)[:20]]
        except Exception as e:  # noqa: BLE001
            out.append(f"{path.name}: schema {xsd.name} could not be loaded: {e}")
    else:
        out.append(f"{path.name}: well-formed (schema {xsd_name} not available locally; set AV_XSD_DIR to validate)") if xsd_name else None
    return [o for o in out if o]


def validate_iiif(path: Path) -> list[str]:
    m = json.loads(Path(path).read_text()); out = []
    for k in ("@context", "id", "type", "label", "items"):
        if k not in m: out.append(f"manifest: missing {k}")
    if m.get("type") != "Manifest": out.append("manifest: type is not Manifest")
    for c in m.get("items", []):
        if c.get("type") != "Canvas" or "duration" not in c: out.append("manifest: canvas without duration")
        for page in c.get("items", []):
            for a in page.get("items", []):
                if a.get("motivation") != "painting": out.append("manifest: canvas item without painting motivation")
    for r in m.get("structures", []):
        if r.get("type") != "Range" or not r.get("items"): out.append("manifest: bad range")
    return out


def validate_bag(bag_dir: Path) -> list[str]:
    bag_dir = Path(bag_dir); out = []
    man = bag_dir / "manifest-sha256.txt"
    if not man.exists():
        return ["bag: manifest-sha256.txt missing"]
    for line in man.read_text().splitlines():
        h, p = line.split("  ", 1)
        f = bag_dir / p
        if not f.exists():
            out.append(f"bag: missing {p}"); continue
        hh = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                hh.update(chunk)
        if hh.hexdigest() != h:
            out.append(f"bag: checksum mismatch {p}")
    return out


def validate_all(out_dir: Path) -> dict[str, list[str]]:
    out_dir = Path(out_dir); res = {}
    if (out_dir / "ebucore.xml").exists(): res["ebucore.xml"] = validate_xml(out_dir / "ebucore.xml", "EBUCore.xsd")
    if (out_dir / "premis.xml").exists(): res["premis.xml"] = validate_xml(out_dir / "premis.xml", "premis.xsd")
    if (out_dir / "mets.xml").exists(): res["mets.xml"] = validate_xml(out_dir / "mets.xml", "mets.xsd")
    if (out_dir / "manifest.json").exists(): res["manifest.json"] = validate_iiif(out_dir / "manifest.json")
    for name in ("schemaorg.json", "annotations.json", "record.json", "annotations.jams"):
        if (out_dir / name).exists():
            try: json.loads((out_dir / name).read_text()); res[name] = []
            except Exception as e: res[name] = [str(e)]  # noqa: BLE001
    return res
