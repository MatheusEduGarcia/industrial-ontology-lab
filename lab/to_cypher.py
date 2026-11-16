"""
Export the RDF graph to Cypher for Neo4j (labelled property graph).

Mapping, kept deliberately simple and explicit:
  * every subject with an rdf:type in the lab namespaces -> node, label = class name
  * literal properties                                    -> node properties
  * object properties between two such nodes              -> relationships (UPPER_SNAKE_CASE)
  * the node key is `iri`, so the export is idempotent (MERGE)

Run:  python -m lab.to_cypher > neo4j/plant.cypher
      python -m lab.to_cypher ontology > neo4j/ontology.cypher   (load plant.cypher first)
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


def _s(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def ontology_to_cypher(onto: Graph | None = None) -> list[str]:
    """
    The ontology itself as nodes, next to the data it describes.

      (:OntologyClass {iri, name, module, definition, examples})
      (:OntologyProperty {iri, name, module, kind, definition})
      (:OperatingState {iri, name, definition})
      (:OntologyClass)-[:SUBCLASS_OF]->(:OntologyClass)
      (:OntologyProperty)-[:DOMAIN]->(:OntologyClass)    where the relation starts
      (:OntologyProperty)-[:RANGE]->(:OntologyClass)     where it ends
      (:OperatingState)-[:CAN_TRANSITION_TO]->(:OperatingState)
      (instance)-[:INSTANCE_OF]->(:OntologyClass)

    With this in the database, an application or an AI agent can ask the graph
    what a label means before it queries the instances.
    """
    from .catalog import terms
    all_terms = terms(onto)
    by_curie = {t["curie"]: t for t in all_terms}
    out = ["CREATE CONSTRAINT ontology_iri IF NOT EXISTS FOR (n:OntologyTerm) REQUIRE n.iri IS UNIQUE;"]
    for t in all_terms:
        label = {"class": "OntologyClass", "relation": "OntologyProperty", "attribute": "OntologyProperty",
                 "state": "OperatingState"}[t["kind"]]
        props = [f"n.name = {_s(t['name'])}", f"n.module = {_s(t['module'])}", f"n.definition = {_s(t['definition'])}"]
        if t["kind"] in ("relation", "attribute"):
            props.append(f"n.kind = {_s(t['kind'])}")
        if t["kind"] == "state":
            props.append(f"n.text = {_s(t['label'])}")
        if t["examples"]:
            props.append("n.examples = [" + ", ".join(_s(e) for e in t["examples"]) + "]")
        out.append(f"MERGE (n:OntologyTerm:{label} {{iri: {_s(t['iri'])}}}) SET {', '.join(props)};")

    def link(a, rel, b):
        out.append(f"MATCH (a:OntologyTerm {{iri: {_s(a)}}}), (b:OntologyTerm {{iri: {_s(b)}}}) MERGE (a)-[:{rel}]->(b);")

    for t in all_terms:
        if t["kind"] == "class":
            for p in t["parents"]:
                link(t["iri"], "SUBCLASS_OF", by_curie[p]["iri"])
        elif t["kind"] == "state":
            for r in t["range"]:
                link(t["iri"], "CAN_TRANSITION_TO", by_curie[r]["iri"])
        else:
            for d in t["domain"]:
                link(t["iri"], "DOMAIN", by_curie[d]["iri"])
            for r in t["range"]:
                if r in by_curie:
                    link(t["iri"], "RANGE", by_curie[r]["iri"])
    out.append("MATCH (n:Resource) UNWIND labels(n) AS l MATCH (c:OntologyClass {name: l}) MERGE (n)-[:INSTANCE_OF]->(c);")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "plant"
    lines = ontology_to_cypher() if which == "ontology" else to_cypher(load_plant(with_ontology=False))
    sys.stdout.write("\n".join(lines) + "\n")
