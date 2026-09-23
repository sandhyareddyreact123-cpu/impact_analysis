## AI Impact Analysis

**Severity:** Low

**Why:**
- No registered downstream dependency found

### Affected services
- None

### Owning teams
- None resolved

### API consumers
- None

### Schema impacts
- None

### Affected tests
- None

### CI gate: not_required

### Analysis warnings
- `malformed_edge` (team3): 2 malformed edge(s) dropped
- `unknown_node` (team3): 'shadow-service' is in the dependency graph but not in the service catalog
- `coverage_gap` (team3): 1 catalog service(s) have no dependency-graph node
- `no_changed_service` (team3): No changed service could be resolved from the PR payload

_Dependency graph `poc-v1` — coverage 90.91% (10/11 catalog services)._