"""
Business questions answered with SPARQL over the plant graph.

Each query crosses at least two domains: that is the point of having a
shared core. None of these questions can be answered by one system alone
(MES, CMMS, QMS, energy monitoring) without a common model of identity.
"""

# 1. Hierarchy: everything inside a site, at any depth (transitive partOf via property path)
ASSETS_IN_SITE = """
SELECT ?asset ?type ?label WHERE {
  ?asset mfg:partOf+ <https://w3id.org/industrial-ontology-lab/id/acme/sao-paulo> ;
         a ?type ; rdfs:label ?label .
  FILTER(?type IN (mfg:Area, mfg:Line, mfg:Equipment, mnt:Component))
} ORDER BY STR(?asset)
"""

# 2. Maintenance x production: unplanned downtime per line and failure mode
DOWNTIME_BY_FAILURE_MODE = """
SELECT ?line ?mode (COUNT(?d) AS ?stops) (SUM(?minutes) AS ?total_min) WHERE {
  ?d a mnt:Downtime ; mnt:planned false ; mnt:causedBy/rdfs:label ?mode ;
     mfg:occurredOn/mfg:partOf/rdfs:label ?line ;
     mfg:startTime ?s ; mfg:endTime ?e .
  BIND((HOURS(?e) * 60 + MINUTES(?e)) - (HOURS(?s) * 60 + MINUTES(?s)) AS ?minutes)
} GROUP BY ?line ?mode ORDER BY DESC(?total_min)
"""

# 3. Maintenance x production x quality: lots made by runs that overlapped a failure, and what QA found
LOTS_HIT_BY_FAILURE = """
SELECT ?lot ?run ?result ?leaks
       (SUM(?hit) AS ?stops_during_run) (GROUP_CONCAT(DISTINCT ?m; separator=", ") AS ?failure_modes)
WHERE {
  ?r a prd:ProductionRun ; rdfs:label ?run ; mfg:occurredOn ?eq ;
     mfg:startTime ?rs ; mfg:endTime ?re ; prd:produced ?l .
  ?l rdfs:label ?lot .
  ?ins qa:inspects ?l ; qa:result ?result .
  OPTIONAL { ?ins qa:hasFinding [ qa:defectType <https://w3id.org/industrial-ontology-lab/id/defect-type/leak> ; qa:defectCount ?leaks ] }
  OPTIONAL {
    ?d a mnt:Downtime ; mnt:planned false ; mfg:occurredOn ?eq ; mnt:causedBy/rdfs:label ?mode ;
       mfg:startTime ?ds ; mfg:endTime ?de .
    FILTER(?ds < ?re && ?de > ?rs)                    # the stop happened inside the run
  }
  BIND(IF(BOUND(?d), 1, 0) AS ?hit)
  BIND(COALESCE(?mode, "-") AS ?m)
} GROUP BY ?lot ?run ?result ?leaks ORDER BY ?lot
"""

# 4. Inventory x quality: genealogy, every lot that consumed a material lot and its inspection result
GENEALOGY_OF_MATERIAL_LOT = """
SELECT ?material_lot ?supplier ?lot ?line ?result WHERE {
  ?ml a inv:MaterialLot ; rdfs:label ?material_lot ; inv:suppliedBy/rdfs:label ?supplier .
  ?run inv:consumed ?ml ; prd:produced/rdfs:label ?lot ;
       mfg:occurredOn/mfg:partOf/rdfs:label ?line .
  ?ins qa:inspects/rdfs:label ?lot ; qa:result ?result .
} ORDER BY ?material_lot ?lot
"""

# 5. Energy x production: kWh per 1,000 good parts per line
ENERGY_PER_PART = """
SELECT ?line ?kwh ?good ((?kwh * 1000 / ?good) AS ?kwh_per_1000) WHERE {
  { SELECT ?line_node (SUM(?g) AS ?good) WHERE {
      ?run a prd:ProductionRun ; prd:goodQty ?g ; mfg:occurredOn/mfg:partOf ?line_node .
    } GROUP BY ?line_node }
  ?c a nrg:Consumption ; nrg:kWh ?kwh ; nrg:measuredBy/nrg:meters ?line_node .
  ?line_node rdfs:label ?line .
} ORDER BY ?kwh_per_1000
"""

# 6. Bridge to the UNS: where do I subscribe to read the live state of every filler?
UNS_TOPICS_FOR_FILLERS = """
SELECT ?equipment ?topic ?value WHERE {
  ?eq a mfg:Equipment ; rdfs:label ?equipment ; mfg:hasDataPoint ?dp .
  FILTER(CONTAINS(STR(?eq), "filler"))
  ?dp mfg:unsTopic ?topic .
  FILTER(STRENDS(?topic, "/state"))
  OPTIONAL { ?dp mfg:lastValue ?value }
} ORDER BY ?topic
"""

# 7. Maintenance: which component does the most frequent failure mode hit, and was it replaced?
COMPONENT_TO_REPLACE = """
SELECT ?mode ?component (COUNT(DISTINCT ?d) AS ?stops) ?order WHERE {
  ?d a mnt:Downtime ; mnt:causedBy ?fm .
  ?fm rdfs:label ?mode ; mnt:affects ?c .
  ?c rdfs:label ?component .
  OPTIONAL { ?mo2 mnt:replaced ?c . BIND(STRAFTER(STR(?mo2), "maintenance-order/") AS ?order) }
} GROUP BY ?mode ?component ?order ORDER BY DESC(?stops)
"""

# ---------------------------------------------------------------------------
# Version 2: questions that need the wider model
# ---------------------------------------------------------------------------

# 8. Core x production: on which lines can each product run?
#    A line qualifies when no required capability is missing from its equipment (double negation).
LINES_CAPABLE_OF_PRODUCT = """
SELECT ?product ?line WHERE {
  ?p a prd:Product ; rdfs:label ?product .
  ?l a mfg:Line ; rdfs:label ?line .
  FILTER NOT EXISTS {
    ?p prd:requiresCapability ?c .
    FILTER NOT EXISTS { ?eq mfg:partOf ?l ; mfg:hasCapability ?c }
  }
} ORDER BY ?product ?line
"""

SHIFT_DAY = "2026-11-10T06:00:00+00:00"


# 9. Maintenance: preventive plans already overdue on a given day, and the stops their component caused since
def overdue_plans(as_of: str = SHIFT_DAY) -> str:
    return """
SELECT ?plan ?component ?equipment ?due ?interval_days (COUNT(DISTINCT ?d) AS ?stops_on_shift) WHERE {
  ?pl a mnt:MaintenancePlan ; rdfs:label ?plan ; mnt:dueDate ?due ; mnt:intervalDays ?interval_days ; mnt:covers ?c .
  ?c rdfs:label ?component ; mfg:partOf/rdfs:label ?equipment .
  FILTER(?due < "%s"^^xsd:dateTime)
  OPTIONAL { ?d a mnt:Downtime ; mnt:causedBy/mnt:affects ?c }
} GROUP BY ?plan ?component ?equipment ?due ?interval_days ORDER BY ?due
""" % as_of


# 10. Quality x inventory: cap torque of every lot against the specification, next to the cap lot it used
TORQUE_VS_SPEC = """
SELECT ?lot ?line ?material_lot ?lower ?upper (COUNT(?v) AS ?samples) (AVG(?v) AS ?mean) (MIN(?v) AS ?lowest)
       (SUM(IF(?v < ?lower || ?v > ?upper, 1, 0)) AS ?out_of_spec) WHERE {
  ?ins qa:inspects ?l ; qa:hasMeasurement ?m .
  ?m qa:ofCharacteristic ?ch ; qa:value ?v .
  ?l rdfs:label ?lot ; prd:lotOf ?p .
  ?spec qa:specFor ?p ; qa:ofCharacteristic ?ch ; qa:lowerLimit ?lower ; qa:upperLimit ?upper .
  ?run prd:produced ?l ; inv:consumed/rdfs:label ?material_lot ; mfg:occurredOn/mfg:partOf/rdfs:label ?line .
} GROUP BY ?lot ?line ?material_lot ?lower ?upper ORDER BY ?lot
"""

# 11. Energy x production: each line against the baseline of the product it made
ENERGY_VS_BASELINE = """
SELECT ?line ?actual ?expected ?tolerance_pct (((?actual - ?expected) * 100 / ?expected) AS ?deviation_pct) WHERE {
  { SELECT ?line_node ?p (SUM(?g) AS ?good) WHERE {
      ?run a prd:ProductionRun ; prd:goodQty ?g ; prd:executes/prd:forProduct ?p ; mfg:occurredOn/mfg:partOf ?line_node .
    } GROUP BY ?line_node ?p }
  ?c a nrg:Consumption ; nrg:kWh ?kwh ; nrg:measuredBy/nrg:meters ?line_node .
  ?b nrg:baselineFor ?p ; nrg:expectedKwhPer1000 ?expected ; nrg:tolerancePct ?tolerance_pct .
  ?line_node rdfs:label ?line .
  BIND(?kwh * 1000 / ?good AS ?actual)
} ORDER BY DESC(?deviation_pct)
"""

# 12. Quality x inventory: where is the remaining stock of material that went into non-conforming lots?
STOCK_TO_QUARANTINE = """
SELECT ?material_lot ?supplier ?location ?where ?quantity (GROUP_CONCAT(DISTINCT ?nc; separator=", ") AS ?because_of) WHERE {
  ?n a qa:NonConformance ; rdfs:label ?nc ; qa:concerns ?l .
  ?run prd:produced ?l ; inv:consumed ?ml .
  ?ml rdfs:label ?material_lot ; inv:suppliedBy/rdfs:label ?supplier .
  ?st inv:stockOf ?ml ; inv:quantity ?quantity ; inv:storedAt ?loc .
  ?loc rdfs:label ?location ; inv:locatedIn/rdfs:label ?where .
} GROUP BY ?material_lot ?supplier ?location ?where ?quantity ORDER BY DESC(?quantity)
"""

# 13. Core: state changes the model says cannot happen (a data or integration problem, found by the model)
ILLEGAL_TRANSITIONS = """
SELECT ?equipment ?from ?to ?when WHERE {
  ?e a mfg:StateChange ; mfg:fromOperatingState ?a ; mfg:toOperatingState ?b ;
     mfg:startTime ?when ; mfg:occurredOn/rdfs:label ?equipment .
  ?a rdfs:label ?from . ?b rdfs:label ?to .
  FILTER NOT EXISTS { ?a mfg:canTransitionTo ?b }
} ORDER BY ?when
"""

# 14. Core x maintenance x quality: who did what
WHO_DID_WHAT = """
SELECT ?person ?role ?kind (COUNT(?e) AS ?events) WHERE {
  ?e mfg:performedBy ?p ; a ?cls .
  ?cls rdfs:label ?kind .
  FILTER(?cls IN (mnt:CorrectiveOrder, mnt:PreventiveOrder, qa:Inspection))
  ?p rdfs:label ?person ; mfg:hasRole/rdfs:label ?role .
} GROUP BY ?person ?role ?kind ORDER BY ?person ?kind
"""

# 15. Maintenance: failure modes seen on the shift whose component has no spare in stock
SPARE_RISK = """
SELECT ?mode ?component ?spare ?stock (COUNT(DISTINCT ?d) AS ?stops) WHERE {
  ?d a mnt:Downtime ; mnt:causedBy ?fm .
  ?fm rdfs:label ?mode ; mnt:affects ?c .
  ?c rdfs:label ?component .
  ?sp mnt:fits ?c ; rdfs:label ?spare ; mnt:stockQty ?stock .
  FILTER(?stock = 0)
} GROUP BY ?mode ?component ?spare ?stock
"""

ALL = {
    "assets_in_site": ASSETS_IN_SITE,
    "downtime_by_failure_mode": DOWNTIME_BY_FAILURE_MODE,
    "lots_hit_by_failure": LOTS_HIT_BY_FAILURE,
    "genealogy_of_material_lot": GENEALOGY_OF_MATERIAL_LOT,
    "energy_per_part": ENERGY_PER_PART,
    "uns_topics_for_fillers": UNS_TOPICS_FOR_FILLERS,
    "component_to_replace": COMPONENT_TO_REPLACE,
    "lines_capable_of_product": LINES_CAPABLE_OF_PRODUCT,
    "overdue_plans": overdue_plans(),
    "torque_vs_spec": TORQUE_VS_SPEC,
    "energy_vs_baseline": ENERGY_VS_BASELINE,
    "stock_to_quarantine": STOCK_TO_QUARANTINE,
    "illegal_transitions": ILLEGAL_TRANSITIONS,
    "who_did_what": WHO_DID_WHAT,
    "spare_risk": SPARE_RISK,
}
