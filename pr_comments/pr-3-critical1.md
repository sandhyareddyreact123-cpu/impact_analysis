## AI Impact Analysis

**Severity:** Critical

**Why:**
- Breaking impact reaches a core financial service

### Affected services
- `customer-archive` — owner: unknown — criticality: standard — depth 1 — path: customer-archive -> customer-api
- `customer-portal` — owner: digital-team — criticality: standard — depth 1 — path: customer-portal -> customer-api
- `finance-ledger` — owner: finance-team — criticality: core_financial — depth 1 — path: finance-ledger -> customer-api
- `fraud-engine` — owner: finance-team — criticality: core_financial — depth 2 — path: fraud-engine -> finance-ledger -> customer-api
- `reporting-service` — owner: analytics-team — criticality: standard — depth 1 — path: reporting-service -> customer-api
- `shadow-service` — owner: unknown — criticality: standard — depth 1 — path: shadow-service -> customer-api

### Owning teams
- analytics-team
- digital-team
- finance-team

### API consumers
- `partner-sdk` (external) — unspecified — **BREAKING**
- `customer-portal` (internal) — GET /api/customers — **BREAKING**
- `customer-sdk-python` (sdk) — GET /api/customers v1.4.0 — **BREAKING**

### Schema impacts
- `customer_contract` — **BREAKING** — readers: finance-ledger, daily-etl — writers: customer-api — pipelines: daily-etl

### Affected tests
- unit: `customer_unit`
- integration: `customer_integration`
- contract: `customer_contract`
- e2e: `customer_e2e`

### CI gate: pending_approval

**Cross-team coordination required — tagging:** @analytics-team, @digital-team, @finance-team

### Analysis warnings
- `malformed_edge` (team3): 2 malformed edge(s) dropped
- `unknown_node` (team3): 'shadow-service' is in the dependency graph but not in the service catalog
- `coverage_gap` (team3): 1 catalog service(s) have no dependency-graph node
- `unresolved_owner` (team3): 2 impacted entit(ies) have no owner in the service catalog
- `unresolved_owner` (team3): 4 impacted entit(ies) have no owner in the service catalog

_Dependency graph `poc-v1` — coverage 90.91% (10/11 catalog services)._