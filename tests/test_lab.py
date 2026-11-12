import socket, time, uuid
import pytest
from rdflib import Graph
from lab.graph import ROOT, load_plant, query
from lab import queries as q
from lab.validate import validate
from lab.to_cypher import to_cypher


@pytest.fixture(scope="module")
def g():
    return load_plant()


def test_assets_in_site(g):
    assert len(query(g, q.ASSETS_IN_SITE)) == 12


def test_downtime_pareto(g):
    top = query(g, q.DOWNTIME_BY_FAILURE_MODE)[0]
    assert top["mode"] == "Seal wear" and int(top["total_min"]) == 54


def test_lots_hit_by_failure(g):
    rows = {r["lot"]: r for r in query(g, q.LOTS_HIT_BY_FAILURE)}
    assert rows["L-1043"]["result"] == "REJECT" and int(rows["L-1043"]["stops_during_run"]) == 3
    assert int(rows["L-1041"]["stops_during_run"]) == 0


def test_genealogy(g):
    bad = {r["lot"] for r in query(g, q.GENEALOGY_OF_MATERIAL_LOT) if r["material_lot"] == "ML-2207"}
    assert bad == {"L-1041", "L-1042", "L-1043"}


def test_energy(g):
    assert [r["line"] for r in query(g, q.ENERGY_PER_PART)] == ["Line 2", "Line 1", "Line 3"]


def test_shacl():
    plant = Graph().parse(ROOT / "data" / "plant.ttl")
    assert validate(plant)[0]
    plant.parse(ROOT / "data" / "broken.ttl")
    ok, rows = validate(plant)
    assert not ok and len(rows) == 8


def test_cypher(g):
    lines = to_cypher(load_plant(with_ontology=False))
    assert lines[0].startswith("CREATE CONSTRAINT") and any("PART_OF" in l for l in lines)


def _broker():
    try:
        socket.create_connection(("localhost", 1883), timeout=1).close(); return True
    except OSError:
        return False


@pytest.mark.skipif(not _broker(), reason="no MQTT broker on localhost:1883")
def test_uns_bridge():
    from lab.uns_bridge import UnsBridge, simulate_plant
    b = UnsBridge(load_plant(), prefix=f"ci-{uuid.uuid4().hex[:4]}")
    b.start(); time.sleep(0.3)
    simulate_plant(prefix=b.prefix, seconds=2)
    time.sleep(0.5); b.stop()
    assert b.messages > 20 and len(b.orphans) == 1
