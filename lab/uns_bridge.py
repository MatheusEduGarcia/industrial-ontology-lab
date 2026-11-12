"""
Live bridge from the Unified Namespace to the knowledge graph.

The UNS carries the *current value* of every data point; the graph knows
*what each data point is*. The bridge joins them through one field only:
mfg:unsTopic. For every MQTT message it

  1. finds the DataPoint whose unsTopic equals the message topic,
  2. updates mfg:lastValue / mfg:lastUpdate on that node,
  3. if it is a state topic and the value changed, adds a mfg:StateChange
     event linked to the owning equipment (so history lands in the model),
  4. records topics that exist in the UNS but not in the model ("orphans"):
     the usual sign that someone added a tag without registering the asset.

Run against a broker:  python -m lab.uns_bridge   (Ctrl+C to stop)
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from rdflib import RDF, Graph, Literal, URIRef, XSD

from .graph import ID, MFG, load_plant

HOST = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))


def _client(cid: str = "") -> mqtt.Client:
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)


class UnsBridge:
    def __init__(self, g: Graph, prefix: str = ""):
        """prefix lets tests run in an isolated topic tree: <prefix>/acme/..."""
        self.g = g
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.lock = threading.Lock()
        self.topic_to_dp: dict[str, URIRef] = {}
        self.dp_to_asset: dict[URIRef, URIRef] = {}
        for dp, topic in g.subject_objects(MFG.unsTopic):
            self.topic_to_dp[str(topic)] = dp
        for asset, dp in g.subject_objects(MFG.hasDataPoint):
            self.dp_to_asset[dp] = asset
        self.orphans: dict[str, str] = {}
        self.messages = 0
        self.events_added = 0
        self.c = _client(f"uns-bridge-{uuid.uuid4().hex[:6]}")
        self.c.on_message = self._on_message

    def start(self, root: str = "acme/#"):
        self.c.connect(HOST, PORT)
        self.c.subscribe(self.prefix + root)
        self.c.loop_start()

    def stop(self):
        self.c.loop_stop()
        self.c.disconnect()

    def _on_message(self, _c, _u, msg):
        topic = msg.topic[len(self.prefix):]
        raw = msg.payload.decode(errors="ignore")
        try:
            value = json.loads(raw)
            value = value.get("value", value) if isinstance(value, dict) else value
        except ValueError:
            value = raw
        now = Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)
        with self.lock:
            self.messages += 1
            dp = self.topic_to_dp.get(topic)
            if dp is None:
                self.orphans[topic] = raw
                return
            previous = self.g.value(dp, MFG.lastValue)
            self.g.set((dp, MFG.lastValue, Literal(value)))
            self.g.set((dp, MFG.lastUpdate, now))
            if topic.endswith("/state") and (previous is None or str(previous) != str(value)):
                ev = ID[f"event/{uuid.uuid4().hex[:10]}"]
                self.g.add((ev, RDF.type, MFG.StateChange))
                self.g.add((ev, MFG.occurredOn, self.dp_to_asset[dp]))
                self.g.add((ev, MFG.toState, Literal(str(value))))
                self.g.add((ev, MFG.startTime, now))
                self.events_added += 1


def simulate_plant(prefix: str = "", seconds: float = 6, period: float = 0.5, seed: int = 1):
    """Publishes UNS traffic for the three fillers, plus one tag nobody registered."""
    rnd = random.Random(seed)
    pre = prefix.rstrip("/") + "/" if prefix else ""
    fillers = ["acme/sao-paulo/packaging/line-1/filler-01",
               "acme/sao-paulo/packaging/line-2/filler-01",
               "acme/curitiba/packaging/line-3/filler-01"]
    state = {f: "RUNNING" for f in fillers}
    p = _client()
    p.connect(HOST, PORT)
    p.loop_start()
    t_end = time.time() + seconds
    while time.time() < t_end:
        for f in fillers:
            if rnd.random() < 0.12:
                state[f] = rnd.choice(["RUNNING", "STOPPED", "FAULTED"]) if state[f] == "RUNNING" else "RUNNING"
            speed = 0.0 if state[f] != "RUNNING" else round(rnd.uniform(440, 500), 1)
            p.publish(pre + f + "/state", json.dumps({"value": state[f]}))
            p.publish(pre + f + "/speed", json.dumps({"value": speed}))
            p.publish(pre + f + "/temperature", json.dumps({"value": round(rnd.uniform(28, 34), 1)}))
        p.publish(pre + "acme/sao-paulo/packaging/line-1/filler-01/vibration_rms", json.dumps({"value": 1.7}))
        time.sleep(period)
    time.sleep(0.5)
    p.loop_stop()
    p.disconnect()


if __name__ == "__main__":
    g = load_plant()
    b = UnsBridge(g)
    b.start()
    print(f"bridging {len(b.topic_to_dp)} modelled topics, Ctrl+C to stop")
    try:
        while True:
            time.sleep(5)
            print(f"{b.messages} msgs, {b.events_added} state events, {len(b.orphans)} orphan topics")
    except KeyboardInterrupt:
        b.stop()
