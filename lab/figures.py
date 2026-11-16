"""
Figures used by the notebooks and the README.

Graph drawings are written as Graphviz DOT and rendered with the `dot` binary
(apt install graphviz / brew install graphviz). The timeline uses matplotlib.

Run:  python -m lab.figures      -> writes docs/img/*.png
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from rdflib import OWL, RDF, RDFS, Graph

from .graph import MFG, MNT, ROOT, load_ontology, load_plant, query

IMG = ROOT / "docs" / "img"
COLORS = {"core": "#7f8c8d", "production": "#2980b9", "maintenance": "#c0392b",
          "quality": "#8e44ad", "energy": "#e67e22", "inventory": "#27ae60"}
LEVEL = {"Enterprise": "#34495e", "Site": "#2c3e50", "Area": "#16a085", "Line": "#2980b9",
         "Equipment": "#7f8c8d", "Component": "#c0392b"}


def render(dot: str, name: str) -> Path:
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"{name}.png"
    subprocess.run(["dot", "-Tpng", "-Gdpi=130", "-o", str(out)], input=dot.encode(), check=True)
    return out


def _short(iri) -> str:
    return str(iri).split("#")[-1].split("/")[-1]


def hierarchy_dot(g: Graph) -> str:
    lines = ['digraph H { rankdir=TB; nodesep=0.25; ranksep=0.45;',
             'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10 fontcolor=white];',
             'edge [color="#999999" arrowhead=none];']
    for node, cls in g.subject_objects(RDF.type):
        c = _short(cls)
        if c in LEVEL and "/id/" in str(node):
            label = g.value(node, RDFS.label)
            lines.append(f'"{node}" [label="{label}\\n{c}" fillcolor="{LEVEL[c]}"];')
    for child, parent in g.subject_objects(MFG.partOf):
        lines.append(f'"{parent}" -> "{child}";')
    return "\n".join(lines + ["}"])


def schema_dot(onto: Graph) -> str:
    def dom(iri):
        return str(iri).split("/")[-1].split("#")[0]
    lines = ['digraph S { rankdir=LR; splines=true; nodesep=0.35; ranksep=0.8;',
             'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 fontcolor=white];',
             'edge [fontname="Helvetica" fontsize=8 color="#555555"];']
    clusters: dict[str, list[str]] = {}
    for c in onto.subjects(RDF.type, OWL.Class):
        clusters.setdefault(dom(c), []).append(_short(c))
    for d, classes in clusters.items():
        lines.append(f'subgraph cluster_{d} {{ label="{d}"; fontname="Helvetica"; color="{COLORS[d]}"; style=dashed;')
        lines += [f'"{c}" [fillcolor="{COLORS[d]}"];' for c in classes]
        lines.append("}")
    for p in onto.subjects(RDF.type, OWL.ObjectProperty):
        d, r = onto.value(p, RDFS.domain), onto.value(p, RDFS.range)
        if d and r and (p, OWL.inverseOf, None) not in onto:
            lines.append(f'"{_short(d)}" -> "{_short(r)}" [label="{_short(p)}"];')
    for c, sup in onto.subject_objects(RDFS.subClassOf):
        if (c, RDF.type, OWL.Class) in onto:
            lines.append(f'"{_short(c)}" -> "{_short(sup)}" [style=dashed color="#bbbbbb" arrowhead=empty];')
    return "\n".join(lines + ["}"])


def timeline(g: Graph, path: Path | None = None):
    """Runs (bars), stops (red/grey) and inspection result per line, for the whole shift."""
    runs = query(g, """SELECT ?line ?run ?s ?e ?res WHERE {
        ?r a prd:ProductionRun ; rdfs:label ?run ; mfg:startTime ?s ; mfg:endTime ?e ;
           mfg:occurredOn/mfg:partOf/rdfs:label ?line ; prd:produced ?l . ?i qa:inspects ?l ; qa:result ?res }""")
    stops = query(g, """SELECT ?line ?s ?e ?planned ?mode WHERE {
        ?d a mnt:Downtime ; mfg:startTime ?s ; mfg:endTime ?e ; mnt:planned ?planned ;
           mfg:occurredOn/mfg:partOf/rdfs:label ?line . OPTIONAL { ?d mnt:causedBy/rdfs:label ?mode } }""")
    t0 = min(r["s"] for r in runs)
    h = lambda t: (t - t0).total_seconds() / 3600
    ylines = sorted({r["line"] for r in runs}, reverse=True)
    y = {l: i for i, l in enumerate(ylines)}
    rescol = {"PASS": "#27ae60", "HOLD": "#f39c12", "REJECT": "#c0392b"}
    fig, ax = plt.subplots(figsize=(11, 3.2))
    for r in runs:
        ax.barh(y[r["line"]], h(r["e"]) - h(r["s"]), left=h(r["s"]), height=0.5,
                color=rescol[r["res"]], alpha=0.35, edgecolor=rescol[r["res"]])
        ax.text((h(r["s"]) + h(r["e"])) / 2, y[r["line"]] + 0.33, f'{r["run"]} · {r["res"]}',
                ha="center", fontsize=8, color=rescol[r["res"]])
    for s in stops:
        col = "#95a5a6" if s["planned"] else ("#c0392b" if s.get("mode") == "Seal wear" else "#34495e")
        ax.barh(y[s["line"]], h(s["e"]) - h(s["s"]), left=h(s["s"]), height=0.5, color=col)
    ax.set_yticks(range(len(ylines)), ylines)
    ax.set_xlabel("hours since 06:00, 10 Nov 2026")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#c0392b", label="seal-wear stop"), Patch(color="#34495e", label="other stop"),
                       Patch(color="#95a5a6", label="planned stop"),
                       Patch(color="#27ae60", alpha=.35, label="run, lot PASS"),
                       Patch(color="#f39c12", alpha=.35, label="run, lot HOLD"),
                       Patch(color="#c0392b", alpha=.35, label="run, lot REJECT")],
              loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=6, fontsize=8, frameon=False)
    ax.set_ylim(-0.6, len(ylines) - 0.2)
    ax.set_title("The shift: runs, stops and the inspection result of each lot")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=130)
    return fig


def bars(rows, label, value, title, xlabel, color, path: Path | None = None):
    rows = sorted(rows, key=lambda r: float(r[value]))
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(rows) + 1))
    vals = [float(r[value]) for r in rows]
    ax.barh([label(r) for r in rows], vals, color=color)
    for i, v in enumerate(vals):
        ax.text(v, i, f"  {v:g}", va="center", fontsize=9)
    ax.set_title(title); ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=130)
    return fig


def pareto(g: Graph, path: Path | None = None):
    from .queries import DOWNTIME_BY_FAILURE_MODE
    return bars(query(g, DOWNTIME_BY_FAILURE_MODE), lambda r: f'{r["line"]} · {r["mode"]}', "total_min",
                "Unplanned downtime by line and failure mode", "minutes", "#c0392b", path)


def energy(g: Graph, path: Path | None = None):
    from .queries import ENERGY_PER_PART
    rows = [dict(r, kwh_per_1000=round(float(r["kwh_per_1000"]), 2)) for r in query(g, ENERGY_PER_PART)]
    return bars(rows, lambda r: r["line"], "kwh_per_1000", "Energy per 1,000 good parts", "kWh", "#e67e22", path)


def torque(g: Graph, path: Path | None = None):
    """Every torque sample per lot against the specification limits, coloured by cap lot."""
    rows = query(g, """SELECT ?lot ?ml ?v ?lo ?hi WHERE {
        ?ins qa:inspects ?l ; qa:hasMeasurement ?m . ?m qa:value ?v ; qa:ofCharacteristic ?ch .
        ?l rdfs:label ?lot ; prd:lotOf ?p . ?s qa:specFor ?p ; qa:ofCharacteristic ?ch ; qa:lowerLimit ?lo ; qa:upperLimit ?hi .
        ?run prd:produced ?l ; inv:consumed/rdfs:label ?ml } ORDER BY ?lot""")
    lots = sorted({r["lot"] for r in rows})
    colors = dict(zip(sorted({r["ml"] for r in rows}), ["#c0392b", "#2980b9", "#27ae60"]))
    fig, ax = plt.subplots(figsize=(8, 3.6))
    seen = set()
    for r in rows:
        ax.scatter(lots.index(r["lot"]), float(r["v"]), color=colors[r["ml"]], s=36, zorder=3,
                   label=f"cap lot {r['ml']}" if r["ml"] not in seen else None)
        seen.add(r["ml"])
    lo, hi = float(rows[0]["lo"]), float(rows[0]["hi"])
    ax.axhline(lo, color="#c0392b", ls="--", lw=1); ax.text(-0.4, lo - 0.035, "below the lower limit (1.40)", fontsize=8, color="#c0392b")
    ax.axhspan(ax.get_ylim()[0], lo, color="#c0392b", alpha=0.07)
    ax.set_xticks(range(len(lots)), lots); ax.set_ylabel("cap removal torque (N·m)")
    ax.set_title("Cap torque per lot against the specification"); ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    if path:
        fig.savefig(path, dpi=130)
    return fig


def baseline(g: Graph, path: Path | None = None):
    from .queries import ENERGY_VS_BASELINE
    rows = sorted(query(g, ENERGY_VS_BASELINE), key=lambda r: r["line"])
    exp, tol = float(rows[0]["expected"]), float(rows[0]["tolerance_pct"])
    fig, ax = plt.subplots(figsize=(7, 3))
    vals = [float(r["actual"]) for r in rows]
    ax.bar([r["line"] for r in rows], vals, color=["#c0392b" if v > exp * (1 + tol / 100) else "#7f8c8d" for v in vals])
    ax.axhline(exp, color="#2c3e50", lw=1); ax.axhspan(exp, exp * (1 + tol / 100), color="#e67e22", alpha=0.15)
    ax.text(0.5, exp * (1 + tol / 100) + 0.12, f"baseline {exp:g} + {tol:g} % tolerance", fontsize=8, ha="center")
    ax.set_xlim(-0.6, len(rows) - 0.4)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_ylabel("kWh per 1,000 good parts"); ax.set_title("Energy against the product baseline")
    ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    if path:
        fig.savefig(path, dpi=130)
    return fig


if __name__ == "__main__":
    g = load_plant()
    print(render(hierarchy_dot(g), "hierarchy"))
    print(render(schema_dot(load_ontology()), "schema"))
    for name, fn in (("timeline", timeline), ("pareto", pareto), ("energy", energy), ("torque", torque), ("baseline", baseline)):
        fn(g, IMG / f"{name}.png"); print(IMG / f"{name}.png")
