"""
House rules for the ontology, checked on every commit.

An ontology rots quietly: a class added without a definition, a property with
no range, a term used in the data that nobody declared. These checks keep the
model readable by people and by AI agents.

  python -m lab.lint      exits 1 and lists the problems, if any
"""
from __future__ import annotations

import sys

from rdflib import OWL, RDF, RDFS, Graph

from .catalog import SKOS, curie, terms
from .graph import BASE, MFG, ROOT, load_ontology

# relations used by more than one class on purpose, so they declare no single domain
SHARED = {"qa:ofCharacteristic"}


def problems(onto: Graph | None = None, data: Graph | None = None) -> list[str]:
    onto = onto or load_ontology()
    data = data if data is not None else Graph().parse(ROOT / "data" / "plant.ttl")
    out = []
    for t in terms(onto):
        if t["kind"] == "state":
            continue
        if not t["label"]:
            out.append(f"{t['curie']}: no label")
        if not t["definition"]:
            out.append(f"{t['curie']}: no definition (rdfs:comment)")
        if t["kind"] == "class" and not t["examples"]:
            out.append(f"{t['curie']}: class without skos:example")
        if t["kind"] != "class":
            if not t["range"]:
                out.append(f"{t['curie']}: no range")
            if not t["domain"] and t["curie"] not in SHARED:
                out.append(f"{t['curie']}: no domain")

    declared = {s for s in onto.subjects() if str(s).startswith(BASE)}
    used = {o for o in data.objects(None, RDF.type)} | set(data.predicates())
    for u in sorted(used):
        if str(u).startswith(BASE) and u not in declared:
            out.append(f"{curie(u)}: used in the data but not declared in the ontology")

    for c in sorted(set(onto.subjects(RDF.type, OWL.Class))):
        if (c, MFG.isAbstract, None) in onto or (c, MFG.populatedBy, None) in onto:
            continue
        family = set(onto.transitive_subjects(RDFS.subClassOf, c))
        if not any((None, RDF.type, k) in data or (None, RDF.type, k) in onto for k in family):
            out.append(f"{curie(c)}: no instance in the sample data (add one, or mark it abstract)")

    for s in onto.subjects(RDF.type, MFG.OperatingState):
        if (s, MFG.canTransitionTo, None) not in onto:
            out.append(f"{curie(s)}: operating state with no way out")
    _ = SKOS
    return out


if __name__ == "__main__":
    found = problems()
    for p in found:
        print("  " + p)
    print(f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
