"""
Builds the sample plant used in every notebook: data/plant.ttl

A fictional company with two sites. The data carries a small story so the
cross-domain queries have something to find:

  * filler-01 on line 1 had three unplanned stops caused by "seal wear"
  * the runs that overlapped those stops produced lots with leak defects
  * those lots also consumed material lot ML-2207 (caps from supplier "Cap Co")
  * line 2 makes the same product with other caps and passes inspection

Version 2 adds evidence from more domains around the same shift:

  * the preventive plan for that seal kit was overdue
  * cap removal torque is low on every lot that used ML-2207
  * part of ML-2207 is still in stock and has to be found
  * line 3 uses far more energy per bottle than the baseline allows

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
        sup = ID[f"supplier/{supplier.lower().replace(' ', '-')}"]
        g.add((sup, RDF.type, INV.Supplier)); g.add((sup, RDFS.label, Literal(supplier)))
        g.add((mlots[code], INV.suppliedBy, sup))

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
    g.add((mo, RDF.type, MNT.CorrectiveOrder))
    g.add((mo, RDFS.label, Literal("MO-0077")))
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
    # =========================================================== version 2
    def thing(path, cls, label):
        n = ID[path]
        g.add((n, RDF.type, cls)); g.add((n, RDFS.label, Literal(label)))
        return n

    def day(y, m, d) -> Literal:
        return Literal(datetime(y, m, d, 8, 0, tzinfo=timezone.utc).isoformat(), datatype=XSD.dateTime)

    # ----------------------------------------------------------- equipment classes and capabilities
    cap = {k: thing(f"capability/{k}", MFG.Capability, lbl) for k, lbl in (
        ("fill-pet-500ml", "Fill 500 ml PET bottles"), ("fill-pet-1l", "Fill 1 l PET bottles"),
        ("cap-28mm", "Apply 28 mm caps"), ("cap-38mm", "Apply 38 mm caps"), ("label-wrap", "Wrap-around labelling"))}
    eq_class = {k: thing(f"equipment-class/{k}", MFG.EquipmentClass, k.title()) for k in ("filler", "capper", "labeler")}
    offers = {"filler": ["fill-pet-500ml"], "capper": ["cap-28mm"], "labeler": ["label-wrap"]}
    for (line_key, kind), node in eq.items():
        g.add((node, MFG.ofClass, eq_class[kind]))
        for c in offers[kind]:
            g.add((node, MFG.hasCapability, cap[c]))
    # line 3 is the flexible one: its filler and capper also handle the 1 l format
    g.add((eq[("L3", "filler")], MFG.hasCapability, cap["fill-pet-1l"]))
    g.add((eq[("L3", "capper")], MFG.hasCapability, cap["cap-38mm"]))

    for c in ("fill-pet-500ml", "cap-28mm", "label-wrap"):
        g.add((product, PRD.requiresCapability, cap[c]))
    juice = thing("product/juice-1l", PRD.Product, "Orange juice 1 l")
    g.add((juice, PRD.idealCycleSeconds, Literal("0.20", datatype=XSD.decimal)))
    for c in ("fill-pet-1l", "cap-38mm", "label-wrap"):
        g.add((juice, PRD.requiresCapability, cap[c]))

    # ----------------------------------------------------------- shifts and a changeover
    for key, site in (("SP", "acme/sao-paulo"), ("CT", "acme/curitiba")):
        sh = thing(f"shift/{key}-20261110-M", PRD.Shift, f"Morning shift {key}")
        g.add((sh, MFG.occurredOn, ID[site])); g.add((sh, MFG.startTime, ts(0))); g.add((sh, MFG.endTime, ts(480)))
    co = thing("changeover/CO-001", PRD.Changeover, "CO-001")
    g.add((co, MFG.occurredOn, ID[lines["L3"]])); g.add((co, MFG.startTime, ts(470))); g.add((co, MFG.endTime, ts(480)))
    g.add((co, PRD.toProduct, juice))

    # ----------------------------------------------------------- people
    role_tech = thing("role/maintenance-technician", MFG.Role, "Maintenance technician")
    role_qi = thing("role/quality-inspector", MFG.Role, "Quality inspector")
    ana = thing("person/ana-lima", MFG.Person, "Ana Lima"); g.add((ana, MFG.hasRole, role_tech))
    bruno = thing("person/bruno-reis", MFG.Person, "Bruno Reis"); g.add((bruno, MFG.hasRole, role_qi))
    g.add((mo, MFG.performedBy, ana))

    # ----------------------------------------------------------- preventive maintenance and spares
    seal, motor = ID[f"{lines['L1']}/filler-01/seal-kit"], ID[f"{lines['L1']}/filler-01/main-motor"]
    for code, comp, interval, last, due in (("PM-SEAL-L1", seal, 30, day(2026, 9, 28), day(2026, 10, 28)),
                                            ("PM-MOTOR-L1", motor, 180, day(2026, 8, 1), day(2027, 1, 28))):
        plan = thing(f"maintenance-plan/{code}", MNT.MaintenancePlan, code)
        g.add((plan, MNT.covers, comp)); g.add((plan, MNT.intervalDays, Literal(interval, datatype=XSD.integer)))
        g.add((plan, MNT.lastExecuted, last)); g.add((plan, MNT.dueDate, due))
    pm = thing("maintenance-order/MO-0061", MNT.PreventiveOrder, "MO-0061")
    g.add((pm, MFG.occurredOn, eq[("L1", "filler")])); g.add((pm, MFG.performedBy, ana))
    g.add((pm, MFG.startTime, day(2026, 8, 1)))
    g.add((pm, MFG.endTime, Literal(datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc).isoformat(), datatype=XSD.dateTime)))
    for code, label, comp, qty in (("SK-28", "Seal kit SK-28", seal, 2), ("MTR-7", "Main motor MTR-7", motor, 0)):
        sp = thing(f"spare-part/{code}", MNT.SparePart, label)
        g.add((sp, MNT.fits, comp)); g.add((sp, MNT.stockQty, Literal(qty, datatype=XSD.integer)))
    g.add((mo, MNT.usedSpare, ID["spare-part/SK-28"]))

    # ----------------------------------------------------------- quality: torque against specification
    torque = thing("characteristic/cap-torque", QA.Characteristic, "Cap removal torque")
    g.add((torque, QA.characteristicUnit, Literal("N·m")))
    spec = thing("specification/water-500ml-cap-torque", QA.Specification, "Cap removal torque, still water 500 ml")
    g.add((spec, QA.ofCharacteristic, torque)); g.add((spec, QA.specFor, product))
    g.add((spec, QA.lowerLimit, Literal("1.40", datatype=XSD.decimal)))
    g.add((spec, QA.upperLimit, Literal("2.00", datatype=XSD.decimal)))
    torques = {
        "1041": [1.52, 1.48, 1.45, 1.50, 1.47], "1042": [1.44, 1.38, 1.41, 1.36, 1.46],
        "1043": [1.33, 1.39, 1.31, 1.42, 1.35], "2041": [1.71, 1.68, 1.74, 1.70, 1.66],
        "2042": [1.69, 1.73, 1.67, 1.72, 1.70], "3041": [1.75, 1.70, 1.72, 1.69, 1.74],
    }
    for num, values in torques.items():
        ins = ID[f"inspection/Q-{num}"]
        g.add((ins, RDFS.label, Literal(f"Q-{num}"))); g.add((ins, MFG.performedBy, bruno))
        for i, v in enumerate(values, start=1):
            m = ID[f"measurement/Q-{num}-T{i}"]
            g.add((m, RDF.type, QA.Measurement)); g.add((m, QA.ofCharacteristic, torque))
            g.add((m, QA.value, Literal(f"{v:.2f}", datatype=XSD.decimal)))
            g.add((ins, QA.hasMeasurement, m))
    for code, num, disposition in (("NC-001", "1042", "UNDER_INVESTIGATION"), ("NC-002", "1043", "SCRAP")):
        nc = thing(f"non-conformance/{code}", QA.NonConformance, code)
        g.add((nc, QA.raisedBy, ID[f"inspection/Q-{num}"])); g.add((nc, QA.concerns, ID[f"lot/L-{num}"]))
        g.add((nc, QA.disposition, Literal(disposition)))

    # ----------------------------------------------------------- energy: carriers and baseline
    elec = thing("energy-carrier/electricity", NRG.EnergyCarrier, "Electricity")
    thing("energy-carrier/compressed-air", NRG.EnergyCarrier, "Compressed air")
    for line in lines.values():
        g.add((ID[f"{line}/energy-meter"], NRG.carrier, elec))
    base = thing("energy-baseline/water-500ml", NRG.EnergyBaseline, "Baseline, still water 500 ml")
    g.add((base, NRG.baselineFor, product))
    g.add((base, NRG.expectedKwhPer1000, Literal("3.5", datatype=XSD.decimal)))
    g.add((base, NRG.tolerancePct, Literal("15", datatype=XSD.decimal)))

    # ----------------------------------------------------------- inventory: where the material is now
    for code, d in (("ML-2207", day(2026, 11, 3)), ("ML-2210", day(2026, 11, 5)), ("ML-2215", day(2026, 11, 6))):
        g.add((mlots[code], INV.receivedOn, d))
    places = {
        "sp-wh-a03": ("Warehouse rack A-03", "acme/sao-paulo"),
        "sp-line1-pou": ("Point of use, line 1", lines["L1"]),
        "ct-wh-b01": ("Warehouse rack B-01", "acme/curitiba"),
    }
    for key, (label, where) in places.items():
        loc = thing(f"storage/{key}", INV.StorageLocation, label)
        g.add((loc, INV.locatedIn, ID[where]))
    for i, (code, place, qty) in enumerate((("ML-2207", "sp-wh-a03", 12000), ("ML-2207", "sp-line1-pou", 1800),
                                            ("ML-2210", "sp-wh-a03", 9000), ("ML-2215", "ct-wh-b01", 15000)), start=1):
        st = ID[f"stock/S-{i:03d}"]
        g.add((st, RDF.type, INV.StockItem)); g.add((st, INV.stockOf, mlots[code]))
        g.add((st, INV.storedAt, ID[f"storage/{place}"])); g.add((st, INV.quantity, Literal(qty, datatype=XSD.integer)))
    return g


if __name__ == "__main__":
    g = build()
    out = ROOT / "data" / "plant.ttl"
    g.serialize(out, format="turtle")
    print(f"{len(g)} triples -> {out.relative_to(ROOT)}")
