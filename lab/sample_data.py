"""
Builds the sample plant used in every notebook: data/plant.ttl

A fictional company with two sites. The data carries a small story so the
cross-domain queries have something to find:

  * filler-01 on line 1 had three unplanned stops caused by "seal wear"
  * the runs that overlapped those stops produced lots with leak defects
  * those lots also consumed material lot ML-2207 (caps from supplier "Cap Co")
  * line 2 makes the same product with other caps and passes inspection

Run:  python -m lab.sample_data
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Literal, Namespace, XSD

from .graph import BASE, INV, MFG, MNT, NRG, PRD, QA, bind_all

ROOT = Path(__file__).resolve().parents[1]
ID = Namespace(BASE + "id/")
T0 = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)


def ts(minutes: float) -> Literal:
    return Literal((T0 + timedelta(minutes=minutes)).isoformat(), datatype=XSD.dateTime)


def build() -> Graph:
    g = Graph()
    bind_all(g)
    g.bind("id", ID)

    def asset(path: str, cls, label: str, parent: str | None):
        node = ID[path]
        g.add((node, RDF.type, cls))
        g.add((node, RDFS.label, Literal(label)))
        g.add((node, MFG.assetId, Literal(path)))
        if parent:
            g.add((node, MFG.partOf, ID[parent]))
        return node

    # ----------------------------------------------------------- hierarchy
    asset("acme", MFG.Enterprise, "ACME Beverages", None)
    asset("acme/sao-paulo", MFG.Site, "São Paulo plant", "acme")
    asset("acme/curitiba", MFG.Site, "Curitiba plant", "acme")
    asset("acme/sao-paulo/packaging", MFG.Area, "Packaging", "acme/sao-paulo")
    asset("acme/curitiba/packaging", MFG.Area, "Packaging", "acme/curitiba")
    lines = {
        "L1": "acme/sao-paulo/packaging/line-1",
        "L2": "acme/sao-paulo/packaging/line-2",
        "L3": "acme/curitiba/packaging/line-3",
    }
    asset(lines["L1"], MFG.Line, "Line 1", "acme/sao-paulo/packaging")
    asset(lines["L2"], MFG.Line, "Line 2", "acme/sao-paulo/packaging")
    asset(lines["L3"], MFG.Line, "Line 3", "acme/curitiba/packaging")
    eq = {}
    for line_key, line in lines.items():
        for kind in ("filler", "capper", "labeler"):
            path = f"{line}/{kind}-01"
            eq[(line_key, kind)] = asset(path, MFG.Equipment, f"{kind.title()} {line_key}", line)

    # components of the line-1 filler
    for comp in ("seal-kit", "main-motor", "valve-block"):
        asset(f"{lines['L1']}/filler-01/{comp}", MNT.Component, comp.replace("-", " ").title(), f"{lines['L1']}/filler-01")

    # ----------------------------------------------------------- data points (bridge to the UNS)
    for (line_key, kind), node in eq.items():
        path = str(node).removeprefix(str(ID))
        for name, unit in (("state", ""), ("speed", "parts/min"), ("temperature", "degC")):
            dp = ID[f"{path}/{name}"]
            g.add((dp, RDF.type, MFG.DataPoint))
            g.add((dp, RDFS.label, Literal(f"{kind} {line_key} {name}")))
            g.add((dp, MFG.unsTopic, Literal(f"{path}/{name}")))
            if unit:
                g.add((dp, MFG.unit, Literal(unit)))
            g.add((node, MFG.hasDataPoint, dp))

    # energy meters per line
    for line_key, line in lines.items():
        m = ID[f"{line}/energy-meter"]
        g.add((m, RDF.type, NRG.EnergyMeter))
        g.add((m, RDFS.label, Literal(f"Energy meter {line_key}")))
        g.add((m, MFG.unsTopic, Literal(f"{line}/energy-meter/kwh")))
        g.add((m, MFG.unit, Literal("kWh")))
        g.add((m, NRG.meters, ID[line]))
        g.add((ID[line], MFG.hasDataPoint, m))

    # ----------------------------------------------------------- vocabulary
    product = ID["product/water-500ml"]
    g.add((product, RDF.type, PRD.Product))
    g.add((product, RDFS.label, Literal("Still water 500 ml")))
    g.add((product, PRD.idealCycleSeconds, Literal("0.12", datatype=XSD.decimal)))

    fm = {}
    for key, label, comp in (("seal-wear", "Seal wear", "seal-kit"),
                             ("jam", "Bottle jam", None),
                             ("motor-overload", "Motor overload", "main-motor")):
        fm[key] = ID[f"failure-mode/{key}"]
        g.add((fm[key], RDF.type, MNT.FailureMode))
        g.add((fm[key], RDFS.label, Literal(label)))
        if comp:
            g.add((fm[key], MNT.affects, ID[f"{lines['L1']}/filler-01/{comp}"]))

    leak = ID["defect-type/leak"]
    g.add((leak, RDF.type, QA.DefectType)); g.add((leak, RDFS.label, Literal("Leak at cap")))
    label_def = ID["defect-type/label-skew"]
    g.add((label_def, RDF.type, QA.DefectType)); g.add((label_def, RDFS.label, Literal("Label skewed")))

    caps = ID["material/cap-28mm"]
    g.add((caps, RDF.type, INV.Material)); g.add((caps, RDFS.label, Literal("Cap 28 mm")))
    mlots = {}
    for code, supplier in (("ML-2207", "Cap Co"), ("ML-2210", "Seal Systems"), ("ML-2215", "Seal Systems")):
        mlots[code] = ID[f"material-lot/{code}"]
        g.add((mlots[code], RDF.type, INV.MaterialLot))
        g.add((mlots[code], RDFS.label, Literal(code)))
        g.add((mlots[code], INV.materialOf, caps))
        g.add((mlots[code], INV.supplier, Literal(supplier)))

    # ----------------------------------------------------------- the shift on 10 Nov 2026
    runs = [  # (id, line, start_min, end_min, good, reject, material lot)
        ("R-1041", "L1", 0, 120, 52000, 310, "ML-2207"),
        ("R-1042", "L1", 120, 240, 44100, 980, "ML-2207"),
        ("R-1043", "L1", 270, 470, 81500, 1720, "ML-2207"),
        ("R-2041", "L2", 0, 230, 104000, 260, "ML-2210"),
        ("R-2042", "L2", 240, 470, 103500, 240, "ML-2210"),
        ("R-3041", "L3", 0, 470, 205000, 610, "ML-2215"),
    ]
    for rid, line_key, a, b, good, rej, mlot in runs:
        wo = ID[f"work-order/WO-{rid[2:]}"]
        g.add((wo, RDF.type, PRD.WorkOrder))
        g.add((wo, PRD.forProduct, product))
        g.add((wo, PRD.targetQty, Literal(good + rej + 1000, datatype=XSD.integer)))
        run = ID[f"run/{rid}"]
        g.add((run, RDF.type, PRD.ProductionRun))
        g.add((run, RDFS.label, Literal(rid)))
        g.add((run, PRD.executes, wo))
        g.add((run, MFG.occurredOn, eq[(line_key, "filler")]))
        g.add((run, MFG.startTime, ts(a))); g.add((run, MFG.endTime, ts(b)))
        g.add((run, PRD.goodQty, Literal(good, datatype=XSD.integer)))
        g.add((run, PRD.rejectQty, Literal(rej, datatype=XSD.integer)))
        lot = ID[f"lot/L-{rid[2:]}"]
        g.add((lot, RDF.type, PRD.Lot)); g.add((lot, RDFS.label, Literal(f"L-{rid[2:]}")))
        g.add((lot, PRD.lotOf, product))
        g.add((run, PRD.produced, lot))
        g.add((run, INV.consumed, mlots[mlot]))

    stops = [  # (line, start, end, failure mode or None, planned)
        ("L1", 180, 195, "seal-wear", False),
        ("L1", 240, 270, None, True),            # lunch
        ("L1", 300, 318, "seal-wear", False),
        ("L1", 410, 431, "seal-wear", False),
        ("L1", 455, 462, "jam", False),
        ("L2", 230, 240, None, True),
        ("L2", 350, 356, "jam", False),
        ("L3", 200, 209, "motor-overload", False),
    ]
    for i, (line_key, a, b, mode, planned) in enumerate(stops, start=1):
        d = ID[f"downtime/D-{i:03d}"]
        g.add((d, RDF.type, MNT.Downtime))
        g.add((d, MFG.occurredOn, eq[(line_key, "filler")]))
        g.add((d, MFG.startTime, ts(a))); g.add((d, MFG.endTime, ts(b)))
        g.add((d, MNT.planned, Literal(planned)))
        if mode:
            g.add((d, MNT.causedBy, fm[mode]))
    mo = ID["maintenance-order/MO-0077"]
    g.add((mo, RDF.type, MNT.MaintenanceOrder))
    g.add((mo, MFG.occurredOn, eq[("L1", "filler")]))
    g.add((mo, MFG.startTime, ts(475))); g.add((mo, MFG.endTime, ts(520)))
    g.add((mo, MNT.resolves, ID["downtime/D-004"]))
    g.add((mo, MNT.replaced, ID[f"{lines['L1']}/filler-01/seal-kit"]))

    inspections = [  # (run, result, leaks, skewed)
        ("R-1041", "PASS", 4, 1), ("R-1042", "HOLD", 37, 0), ("R-1043", "REJECT", 61, 2),
        ("R-2041", "PASS", 1, 3), ("R-2042", "PASS", 0, 2), ("R-3041", "PASS", 2, 1),
    ]
    for rid, result, leaks, skew in inspections:
        ins = ID[f"inspection/Q-{rid[2:]}"]
        g.add((ins, RDF.type, QA.Inspection))
        g.add((ins, QA.inspects, ID[f"lot/L-{rid[2:]}"]))
        g.add((ins, QA.result, Literal(result)))
        for dtype, n in ((leak, leaks), (label_def, skew)):
            if n:
                f = ID[f"finding/Q-{rid[2:]}-{str(dtype).rsplit('/', 1)[1]}"]
                g.add((f, RDF.type, QA.Finding))
                g.add((f, QA.defectType, dtype))
                g.add((f, QA.defectCount, Literal(n, datatype=XSD.integer)))
                g.add((ins, QA.hasFinding, f))

    for i, (line_key, kwh) in enumerate((("L1", 612.0), ("L2", 655.0), ("L3", 1180.0))):
        c = ID[f"consumption/E-{line_key}-20261110"]
        g.add((c, RDF.type, NRG.Consumption))
        g.add((c, NRG.measuredBy, ID[f"{lines[line_key]}/energy-meter"]))
        g.add((c, MFG.occurredOn, ID[lines[line_key]]))
        g.add((c, MFG.startTime, ts(0))); g.add((c, MFG.endTime, ts(480)))
        g.add((c, NRG.kWh, Literal(f"{kwh}", datatype=XSD.decimal)))
    return g


if __name__ == "__main__":
    g = build()
    out = ROOT / "data" / "plant.ttl"
    g.serialize(out, format="turtle")
    print(f"{len(g)} triples -> {out.relative_to(ROOT)}")
