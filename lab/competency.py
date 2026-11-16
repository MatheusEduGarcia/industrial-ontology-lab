"""
Competency questions: what the ontology must be able to answer.

A competency question is a business question written before the model, used
to decide what goes into it and, afterwards, to prove that it is enough. Each
one here has the query that answers it and a check on the result, so the list
runs as a test: if a change to the ontology or to the data breaks an answer,
CI says which question was lost.

  run(g)                 one row per question: answered or not, and the answer
  python -m lab.competency   prints the table and writes docs/competency_questions.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from rdflib import RDF, Graph, Literal, XSD

from . import queries as q
from .graph import ID, MFG, ROOT, load_plant, query


def _with_state_changes(g: Graph) -> Graph:
    """A copy of the graph with one legal and one impossible state change, to exercise CQ15."""
    h = Graph()
    for t in g:
        h.add(t)
    filler = ID["acme/sao-paulo/packaging/line-1/filler-01"]
    for a, b, minute in ((MFG.Running, MFG.Faulted, 0), (MFG.Faulted, MFG.Running, 5)):
        ev = ID[f"event/{uuid.uuid5(uuid.NAMESPACE_URL, str(a) + str(b)).hex[:10]}"]
        h.add((ev, RDF.type, MFG.StateChange)); h.add((ev, MFG.occurredOn, filler))
        h.add((ev, MFG.fromOperatingState, a)); h.add((ev, MFG.toOperatingState, b))
        h.add((ev, MFG.startTime, Literal(datetime(2026, 11, 10, 9, minute, tzinfo=timezone.utc).isoformat(), datatype=XSD.dateTime)))
    return h


QUESTIONS = [
    dict(id="CQ01", modules="core", question="What exists inside the São Paulo plant, at any depth?",
         sparql=q.ASSETS_IN_SITE, check=lambda r: len(r) == 12,
         answer=lambda r: f"{len(r)} assets: 1 area, 2 lines, 6 machines and 3 components"),
    dict(id="CQ02", modules="maintenance, core", question="Which failure mode cost the most unplanned downtime, and on which line?",
         sparql=q.DOWNTIME_BY_FAILURE_MODE, check=lambda r: r[0]["mode"] == "Seal wear" and int(r[0]["total_min"]) == 54,
         answer=lambda r: f"{r[0]['mode']} on {r[0]['line']}: {r[0]['stops']} stops, {r[0]['total_min']} min"),
    dict(id="CQ03", modules="maintenance", question="Which component does that failure mode hit, and was it replaced?",
         sparql=q.COMPONENT_TO_REPLACE, check=lambda r: r[0]["component"] == "Seal Kit" and r[0]["order"] == "MO-0077",
         answer=lambda r: f"{r[0]['component']}, replaced by {r[0]['order']}"),
    dict(id="CQ04", modules="maintenance, production, quality", question="Which lots were made while those stops were happening, and what did inspection decide?",
         sparql=q.LOTS_HIT_BY_FAILURE,
         check=lambda r: {x["lot"]: (x["result"], int(x["stops_during_run"])) for x in r}["L-1043"] == ("REJECT", 3),
         answer=lambda r: "; ".join(f"{x['lot']} {x['result']} ({x['stops_during_run']} stops)" for x in r if int(x["stops_during_run"]) and x["result"] != "PASS")),
    dict(id="CQ05", modules="inventory, quality", question="Which product lots consumed cap lot ML-2207, and how did they fare?",
         sparql=q.GENEALOGY_OF_MATERIAL_LOT,
         check=lambda r: {x["lot"] for x in r if x["material_lot"] == "ML-2207"} == {"L-1041", "L-1042", "L-1043"},
         answer=lambda r: ", ".join(f"{x['lot']} {x['result']}" for x in r if x["material_lot"] == "ML-2207")),
    dict(id="CQ06", modules="energy, production", question="Which line uses the most energy per thousand good parts?",
         sparql=q.ENERGY_PER_PART, check=lambda r: r[-1]["line"] == "Line 3",
         answer=lambda r: f"{r[-1]['line']}: {float(r[-1]['kwh_per_1000']):.2f} kWh per 1,000"),
    dict(id="CQ07", modules="core", question="Where do I subscribe to read the live state of every filler?",
         sparql=q.UNS_TOPICS_FOR_FILLERS, check=lambda r: len(r) == 3 and all(x["topic"].endswith("/state") for x in r),
         answer=lambda r: f"{len(r)} topics, for example {r[0]['topic']}"),
    dict(id="CQ08", modules="core, production", question="On which lines can orange juice 1 l run?",
         sparql=q.LINES_CAPABLE_OF_PRODUCT,
         check=lambda r: [x["line"] for x in r if x["product"] == "Orange juice 1 l"] == ["Line 3"],
         answer=lambda r: "only " + ", ".join(x["line"] for x in r if x["product"] == "Orange juice 1 l")),
    dict(id="CQ09", modules="maintenance", question="Was any preventive plan overdue on the day of the shift?",
         sparql=q.overdue_plans(), check=lambda r: [x["plan"] for x in r] == ["PM-SEAL-L1"] and int(r[0]["stops_on_shift"]) == 3,
         answer=lambda r: f"{r[0]['plan']} for the {r[0]['component']} of {r[0]['equipment']}, due {str(r[0]['due'])[:10]}; that component caused {r[0]['stops_on_shift']} stops"),
    dict(id="CQ10", modules="quality, inventory", question="Which lots have cap torque below specification, and which cap lot did they use?",
         sparql=q.TORQUE_VS_SPEC,
         check=lambda r: {x["lot"] for x in r if int(x["out_of_spec"])} == {"L-1042", "L-1043"},
         answer=lambda r: "; ".join(f"{x['lot']}: {x['out_of_spec']} of {x['samples']} samples, cap lot {x['material_lot']}" for x in r if int(x["out_of_spec"]))),
    dict(id="CQ11", modules="energy, production", question="Which line is outside the energy baseline of the product it made?",
         sparql=q.ENERGY_VS_BASELINE,
         check=lambda r: [x["line"] for x in r if float(x["deviation_pct"]) > float(x["tolerance_pct"])] == ["Line 3"],
         answer=lambda r: f"{r[0]['line']}: {float(r[0]['deviation_pct']):.0f} % above the baseline (tolerance {float(r[0]['tolerance_pct']):.0f} %)"),
    dict(id="CQ12", modules="quality, inventory", question="Where is the remaining stock of material that went into non-conforming lots?",
         sparql=q.STOCK_TO_QUARANTINE, check=lambda r: sum(int(x["quantity"]) for x in r) == 13800 and len(r) == 2,
         answer=lambda r: "; ".join(f"{x['quantity']} of {x['material_lot']} at {x['location']}" for x in r)),
    dict(id="CQ13", modules="core, maintenance, quality", question="Who performed the maintenance orders and the inspections?",
         sparql=q.WHO_DID_WHAT, check=lambda r: any(x["person"] == "Ana Lima" and x["kind"] == "Corrective order" for x in r),
         answer=lambda r: "; ".join(f"{x['person']} ({x['role']}): {x['events']} x {x['kind']}" for x in r)),
    dict(id="CQ14", modules="maintenance", question="Which failure mode seen on the shift hits a component with no spare in stock?",
         sparql=q.SPARE_RISK, check=lambda r: len(r) == 1 and r[0]["mode"] == "Motor overload",
         answer=lambda r: f"{r[0]['mode']}: {r[0]['spare']} has {r[0]['stock']} in stock"),
    dict(id="CQ15", modules="core", question="Did any equipment report a state change the model says is impossible?",
         sparql=q.ILLEGAL_TRANSITIONS, prepare=_with_state_changes,
         check=lambda r: len(r) == 1 and (r[0]["from"], r[0]["to"]) == ("FAULTED", "RUNNING"),
         answer=lambda r: f"{r[0]['equipment']}: {r[0]['from']} to {r[0]['to']} without a reset (1 of 2 changes injected for the test)"),
]


def run(g: Graph | None = None) -> list[dict]:
    g = g or load_plant()
    rows = []
    for cq in QUESTIONS:
        result = query(cq["prepare"](g) if "prepare" in cq else g, cq["sparql"])
        try:
            ok = bool(cq["check"](result))
            answer = cq["answer"](result) if ok else "NOT ANSWERED"
        except (IndexError, KeyError, TypeError, ValueError):
            ok, answer = False, "NOT ANSWERED"
        rows.append({"id": cq["id"], "question": cq["question"], "modules": cq["modules"], "answered": ok, "answer": answer})
    return rows


def markdown(rows: list[dict]) -> str:
    md = ["# Competency questions", "",
          "Generated by `python -m lab.competency`. Each question is answered by a query in `lab/queries.py` "
          "and checked in `tests/`, so this table is also a test report.", "",
          "| # | Question | Modules it crosses | Answer from the sample plant |", "|---|---|---|---|"]
    md += [f"| {r['id']} | {r['question']} | {r['modules']} | {r['answer']} |" for r in rows]
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    rows = run()
    for r in rows:
        print(f"{'ok ' if r['answered'] else 'FAIL'} {r['id']}  {r['question']}\n        {r['answer']}")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "competency_questions.md").write_text(markdown(rows), encoding="utf-8")
    raise SystemExit(0 if all(r["answered"] for r in rows) else 1)
