"""Standard metadata exports from one analysis folder.

The analysis writes ``segments.json`` (automatic, overwritten on every run) and reads
``curated.json`` (human, never written by the analysis). :func:`record.build_record` merges the
two into one canonical *record* with five layers: descriptive, technical, structural, rights,
provenance. Every export below is a view of that record:

- :mod:`ebucore`   EBUCore 1.10 XML, the master archival record
- :mod:`iiif`      IIIF Presentation 3 manifest with ranges and W3C Web Annotations, for players and catalogs
- :mod:`schemaorg` schema.org JSON-LD for the catalog page
- :mod:`provenance` PREMIS 3 events: which tool and model produced which layer, with parameters
- :mod:`bag`       a BagIt bag with checksums, ready to deposit
- :mod:`validate`  well-formedness and schema checks for all of the above
"""
from .record import build_record, load_curated  # noqa: F401
from .writer import write_all  # noqa: F401
