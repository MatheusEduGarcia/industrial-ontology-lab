// Lots made by runs that overlapped an unplanned stop, with the material lot they consumed
MATCH (r:ProductionRun)-[:OCCURRED_ON]->(eq:Equipment),
      (r)-[:PRODUCED]->(lot:Lot)<-[:INSPECTS]-(ins:Inspection),
      (r)-[:CONSUMED]->(ml:MaterialLot)
OPTIONAL MATCH (d:Downtime {planned: false})-[:OCCURRED_ON]->(eq), (d)-[:CAUSED_BY]->(fm:FailureMode)
  WHERE d.startTime < r.endTime AND d.endTime > r.startTime
RETURN lot.name, ml.name, ml.supplier, ins.result, count(d) AS stops, collect(DISTINCT fm.name) AS modes
ORDER BY lot.name;
