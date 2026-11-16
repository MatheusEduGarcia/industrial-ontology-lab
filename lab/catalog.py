"""
The ontology as something a person or an AI agent can read.

An agent that is about to query a plant graph has the same problem as a new
engineer: it does not know which classes exist, what each one means, or how
they connect. The definitions and examples written in the .ttl files answer
that, and this module serves them in three forms:

  terms()              every class, property and operating state as a dict
  describe("Downtime") one term in full: definition, examples, parents, what
                       it links to and what links to it (inherited included)
  schema_card()        the whole model as compact text, sized for a prompt

  python -m lab.catalog   writes docs/ontology_reference.md and ontology/catalog.json
"""
from __future__ import annotations

import json

from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef

from .graph import BASE, DOMAINS, MFG, ROOT, load_ontology

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
KINDS = {OWL.Class: "class", OWL.ObjectProperty: "relation", OWL.DatatypeProperty: "attribute"}


def _module(iri) -> str:
    return str(iri)[len(BASE):].split("#")[0]


def _name(iri) -> str:
    return str(iri).split("#")[-1]


def curie(iri) -> str:
    short = {"core": "mfg", "production": "prd", "maintenance": "mnt", "quality": "qa", "energy": "nrg", "inventory": "inv"}
    return f"{short.get(_module(iri), _module(iri))}:{_name(iri)}" if str(iri).startswith(BASE) else _name(iri)


def terms(g: Graph | None = None) -> list[dict]:
    g = g or load_ontology()
    out = []
    for rdf_type, kind in KINDS.items():
        for t in sorted(set(g.subjects(RDF.type, rdf_type))):
            if not str(t).startswith(BASE):
                continue
            out.append({
                "name": _name(t), "curie": curie(t), "iri": str(t), "kind": kind, "module": _module(t),
                "label": str(g.value(t, RDFS.label) or ""), "definition": str(g.value(t, RDFS.comment) or ""),
                "examples": [str(e) for e in g.objects(t, SKOS.example)],
                "parents": [curie(p) for p in g.objects(t, RDFS.subClassOf)],
                "domain": [curie(d) for d in g.objects(t, RDFS.domain)],
                "range": [curie(r) for r in g.objects(t, RDFS.range)],
                "abstract": (t, MFG.isAbstract, None) in g,
                "transitive": (t, RDF.type, OWL.TransitiveProperty) in g,
            })
    for st in sorted(g.subjects(RDF.type, MFG.OperatingState)):
        out.append({"name": _name(st), "curie": curie(st), "iri": str(st), "kind": "state", "module": "core",
                    "label": str(g.value(st, RDFS.label)), "definition": str(g.value(st, RDFS.comment) or ""),
                    "examples": [], "parents": ["mfg:OperatingState"], "domain": [],
                    "range": [curie(x) for x in g.objects(st, MFG.canTransitionTo)], "abstract": False, "transitive": False})
    return out


def _ancestors(g: Graph, cls: URIRef) -> list[URIRef]:
    return [c for c in g.transitive_objects(cls, RDFS.subClassOf)]


def describe(name: str, g: Graph | None = None) -> str:
    """Everything about one term, as text. Accepts 'Downtime', 'mnt:Downtime' or a full IRI."""
    g = g or load_ontology()
    all_terms = terms(g)
    hit = [t for t in all_terms if name in (t["name"], t["curie"], t["iri"])]
    if not hit:
        close = sorted(t["curie"] for t in all_terms if name.lower() in t["name"].lower())
        return f"No term named '{name}'." + (f" Did you mean: {', '.join(close)}?" if close else "")
    t = hit[0]
    lines = [f"{t['curie']}  ({t['kind']}, module {t['module']})", f"  {t['definition']}"]
    if t["examples"]:
        lines.append(f"  Examples: {'; '.join(t['examples'])}")
    if t["kind"] == "class":
        iri = URIRef(t["iri"])
        chain = _ancestors(g, iri)
        if len(chain) > 1:
            lines.append("  Is a: " + " > ".join(curie(c) for c in chain[1:]))
        subs = sorted(curie(s) for s in g.subjects(RDFS.subClassOf, iri))
        if subs:
            lines.append("  Subclasses: " + ", ".join(subs))
        outgoing = [p for p in all_terms if p["kind"] != "class" and any(curie(c) in p["domain"] for c in chain)]
        incoming = [p for p in all_terms if p["kind"] == "relation" and any(curie(c) in p["range"] for c in chain)]
        for title, props, arrow in (("Has", outgoing, "->"), ("Is pointed at by", incoming, "<-")):
            if props:
                lines.append(f"  {title}:")
                for p in sorted(props, key=lambda x: x["curie"]):
                    other = p["range"] if arrow == "->" else p["domain"]
                    lines.append(f"    {p['curie']} {arrow} {', '.join(other) or 'any'}   {p['definition']}")
    elif t["kind"] == "state":
        lines.append("  Can transition to: " + (", ".join(t["range"]) or "nothing"))
    else:
        lines.append(f"  From {', '.join(t['domain']) or 'any'} to {', '.join(t['range']) or 'any'}"
                     + ("  (transitive)" if t["transitive"] else ""))
    return "\n".join(lines)


def schema_card(modules: list[str] | None = None, g: Graph | None = None) -> str:
    """The model as compact text: one line per class with its definition, then its relations."""
    g = g or load_ontology()
    all_terms = terms(g)
    out = []
    for m in ["core"] + DOMAINS:
        if modules and m not in modules:
            continue
        out.append(f"## {m}")
        for c in [t for t in all_terms if t["module"] == m and t["kind"] == "class"]:
            parent = f" (is a {c['parents'][0]})" if c["parents"] else ""
            out.append(f"{c['curie']}{parent}: {c['definition']}")
            for p in [t for t in all_terms if t["kind"] != "class" and c["curie"] in t["domain"]]:
                out.append(f"  .{p['curie']} -> {', '.join(p['range']) or 'literal'}")
        states = [t for t in all_terms if t["module"] == m and t["kind"] == "state"]
        if states:
            out.append("operating states: " + "; ".join(f"{s['label']} -> {', '.join(_name_of(all_terms, r) for r in s['range'])}" for s in states))
        out.append("")
    return "\n".join(out)


def _name_of(all_terms, cur):
    return next((t["label"] for t in all_terms if t["curie"] == cur), cur)


def metrics(g: Graph | None = None) -> list[dict]:
    all_terms = terms(g)
    rows = []
    for m in ["core"] + DOMAINS:
        mine = [t for t in all_terms if t["module"] == m]
        rows.append({"module": m, "classes": sum(t["kind"] == "class" for t in mine),
                     "relations": sum(t["kind"] == "relation" for t in mine),
                     "attributes": sum(t["kind"] == "attribute" for t in mine),
                     "with definition": sum(bool(t["definition"]) for t in mine),
                     "terms": len(mine)})
    return rows


def reference_markdown(g: Graph | None = None) -> str:
    all_terms = terms(g)
    md = ["# Ontology reference", "",
          "Generated by `python -m lab.catalog` from the `.ttl` files. Do not edit by hand.", ""]
    for m in ["core"] + DOMAINS:
        mine = [t for t in all_terms if t["module"] == m]
        md += [f"## {m}", "", "### Classes", "", "| Class | Is a | Definition | Examples |", "|---|---|---|---|"]
        md += [f"| `{t['curie']}` | {', '.join(f'`{p}`' for p in t['parents'])} | {t['definition']} | {'; '.join(t['examples'])} |"
               for t in mine if t["kind"] == "class"]
        md += ["", "### Relations and attributes", "", "| Term | Kind | From | To | Definition |", "|---|---|---|---|---|"]
        md += [f"| `{t['curie']}` | {t['kind']} | {', '.join(f'`{d}`' for d in t['domain'])} | {', '.join(f'`{r}`' for r in t['range'])} | {t['definition']} |"
               for t in mine if t["kind"] in ("relation", "attribute")]
        states = [t for t in mine if t["kind"] == "state"]
        if states:
            md += ["", "### Operating states", "", "| State | Meaning | Can transition to |", "|---|---|---|"]
            md += [f"| `{t['label']}` | {t['definition']} | {', '.join(_name_of(all_terms, r) for r in t['range'])} |" for t in states]
        md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "ontology_reference.md").write_text(reference_markdown(), encoding="utf-8")
    (ROOT / "ontology" / "catalog.json").write_text(json.dumps(terms(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for row in metrics():
        print(row)
