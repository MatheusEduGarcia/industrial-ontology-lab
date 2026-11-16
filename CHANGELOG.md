# Changelog

## 2.0.0

The model becomes readable by people and by AI agents, and grows where a business question needed it.

**Ontology**
- Every term has a label and a definition; every class has an example (120 terms).
- Core: `EquipmentClass`, `Capability`, `OperatingState` with allowed transitions, `Person`, `Role`.
- Production: `Shift`, `Changeover`, `requiresCapability`.
- Maintenance: `CorrectiveOrder`, `PreventiveOrder`, `MaintenancePlan`, `SparePart`.
- Quality: `Characteristic`, `Specification`, `Measurement`, `NonConformance`.
- Energy: `EnergyCarrier`, `EnergyBaseline`.
- Inventory: `Supplier`, `StorageLocation`, `StockItem`.

**Breaking**
- `inv:supplier` (text) is replaced by `inv:suppliedBy` (a link to an `inv:Supplier`).
- `MO-0077` is now a `mnt:CorrectiveOrder`; queries that matched `mnt:MaintenanceOrder` by exact type need `rdfs:subClassOf*` or no type.

**Tooling**
- `lab.catalog`: describe a term, generate a schema card for a prompt, write the reference and a JSON catalog.
- `lab.lint`: house rules, including terms used in the data but not declared.
- `lab.competency`: 15 competency questions that run as tests.
- `lab.to_cypher ontology`: the ontology as nodes in Neo4j, with instances linked to their classes.
- The UNS bridge records the state left and entered, so impossible transitions can be listed.

**Study material**
- Notebooks 06 and 07, six new SHACL contracts and `data/broken_v2.ttl`.

## 0.1.0

Core plus five domain extensions, sample plant, SHACL contracts, seven cross-domain queries, UNS bridge, Neo4j export, five study notebooks.
