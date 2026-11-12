"""
Export the RDF graph to Cypher for Neo4j (labelled property graph).

Mapping, kept deliberately simple and explicit:
  * every subject with an rdf:type in the lab namespaces -> node, label = class name
  * literal properties                                    -> node properties
  * object properties between two such nodes              -> relationships (UPPER_SNAKE_CASE)
  * the node key is `iri`, so the export is idempotent (MERGE)

Run:  python -m lab.to_cypher > neo4j/plant.cypher
"""
from __future__ import annotations

import re
import sys

from rdflib import RDF, RDFS, Graph, Literal, URIRef

from .graph import BASE, load_plant


def _local(iri: str) -> str:
    return re.split(r"[#/]", iri)[-1]


def _rel(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _lit(v: Literal) -> str:
    py = v.toPython()
    if isinstance(py, bool):
        return "true" if py else "false"
    if isinstance(py, (int, float)):
        return repr(py)
    if hasattr(py, "isoformat"):
        return f"datetime('{py.isoformat()}')"
    try:
        return repr(float(py)) if str(v.datatype).endswith("decimal") else "'" + str(py).replace("'", "\\'") + "'"
    except (TypeError, ValueError):
        return "'" + str(py).replace("'", "\\'") + "'"


def to_cypher(g: Graph) -> list[str]:
    nodes = {}
    for s, t in g.subject_objects(RDF.type):
        if isinstance(s, URIRef) and str(t).startswith(BASE) and str(s).startswith(BASE + "id/"):
            nodes.setdefault(s, set()).add(_local(str(t)))
    out = ["CREATE CONSTRAINT node_iri IF NOT EXISTS FOR (n:Resource) REQUIRE n.iri IS UNIQUE;"]
    for s, labels in sorted(nodes.items()):
        props = {"iri": f"'{s}'"}
        for p, o in g.predicate_objects(s):
            if isinstance(o, Literal):
                key = "name" if p == RDFS.label else _local(str(p))
                props[key] = _lit(o)
        lbl = ":".join(["Resource"] + sorted(labels))
        sets = ", ".join(f"n.{k} = {v}" for k, v in props.items() if k != "iri")
        out.append(f"MERGE (n:{lbl} {{iri: {props['iri']}}})" + (f" SET {sets};" if sets else ";"))
    for s in sorted(nodes):
        for p, o in g.predicate_objects(s):
            if isinstance(o, URIRef) and o in nodes and p != RDF.type:
                out.append(f"MATCH (a:Resource {{iri: '{s}'}}), (b:Resource {{iri: '{o}'}}) "
                           f"MERGE (a)-[:{_rel(_local(str(p)))}]->(b);")
    return out


if __name__ == "__main__":
    lines = to_cypher(load_plant(with_ontology=False))
    sys.stdout.write("\n".join(lines) + "\n")
