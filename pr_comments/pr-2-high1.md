## AI Impact Analysis

**Severity:** High

**Why:**
- Breaking API contract change
- External consumer affected

### Affected services
- `order-analytics` — owner: analytics-team — criticality: standard — depth 3 — path: order-analytics -> order-notifications -> order-portal -> order-api
- `order-notifications` — owner: platform-team — criticality: standard — depth 2 — path: order-notifications -> order-portal -> order-api
- `order-portal` — owner: digital-team — criticality: standard — depth 1 — path: order-portal -> order-api

### Owning teams
- analytics-team
- digital-team
- platform-team
- sdk-guild

### API consumers
- `partner-order-sdk` (external) — unspecified — **BREAKING**
- `mobile-checkout` (internal) — GET /api/orders — **BREAKING**
- `order-portal` (internal) — GET /api/orders — **BREAKING**
- `order-sdk-dotnet` (sdk) — GET /api/orders v2.3.0 — **BREAKING**

### Schema impacts
- None

### Affected tests
- contract: `order_contract`
- e2e: `order_e2e`

### CI gate: not_required

**Cross-team coordination required — tagging:** @analytics-team, @digital-team, @platform-team, @sdk-guild

### Analysis warnings
- `malformed_edge` (team3): 2 malformed edge(s) dropped
- `unknown_node` (team3): 'shadow-service' is in the dependency graph but not in the service catalog
- `coverage_gap` (team3): 1 catalog service(s) have no dependency-graph node
- `unknown_consumer_type` (team3): consumer 'mobile-checkout' has type 'mobile'; treated as internal
- `unresolved_owner` (team3): 2 impacted entit(ies) have no owner in the service catalog

_Dependency graph `poc-v1` — coverage 90.91% (10/11 catalog services)._