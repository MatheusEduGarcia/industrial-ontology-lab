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
  ?ml a inv:MaterialLot ; rdfs:label ?material_lot ; inv:supplier ?supplier .
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
  OPTIONAL { ?mo2 a mnt:MaintenanceOrder ; mnt:replaced ?c . BIND(STRAFTER(STR(?mo2), "maintenance-order/") AS ?order) }
} GROUP BY ?mode ?component ?order ORDER BY DESC(?stops)
"""

ALL = {
    "assets_in_site": ASSETS_IN_SITE,
    "downtime_by_failure_mode": DOWNTIME_BY_FAILURE_MODE,
    "lots_hit_by_failure": LOTS_HIT_BY_FAILURE,
    "genealogy_of_material_lot": GENEALOGY_OF_MATERIAL_LOT,
    "energy_per_part": ENERGY_PER_PART,
    "uns_topics_for_fillers": UNS_TOPICS_FOR_FILLERS,
    "component_to_replace": COMPONENT_TO_REPLACE,
}
