"""SHACL validation of instance data against the data contracts in shapes/."""
from __future__ import annotations

from pyshacl import validate as _validate
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from .graph import ROOT, load_ontology


def shapes() -> Graph:
    return Graph().parse(ROOT / "shapes" / "shapes.ttl")


def validate(data: Graph) -> tuple[bool, list[dict]]:
    """Validate with the ontology loaded (so sh:class sees subclasses). Returns (conforms, violations)."""
    conforms, report, _ = _validate(data, shacl_graph=shapes(), ont_graph=load_ontology(),
                                    inference="rdfs", allow_warnings=True, advanced=True)
    rows = []
    for r in report.subjects(predicate=None, object=SH.ValidationResult):
        focus = report.value(r, SH.focusNode)
        path = report.value(r, SH.resultPath)
        msg = report.value(r, SH.resultMessage)
        rows.append({
            "focus": str(focus).rsplit("/id/", 1)[-1],
            "path": str(path).rsplit("#", 1)[-1] if isinstance(path, URIRef) else "",
            "message": str(msg),
        })
    return conforms, sorted(rows, key=lambda x: (x["focus"], x["path"]))
