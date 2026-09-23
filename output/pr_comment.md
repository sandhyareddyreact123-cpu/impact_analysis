## AI Impact Analysis
**Severity:** Critical
**Commit:** critical1

### Affected services
- customer-portal (digital-team)
- finance-ledger (finance-team)
- reporting-service (analytics-team)

### API consumers
- partner-sdk (external)

### Schema impacts
- customer_contract: readers=finance-ledger, daily-etl; writers=customer-api

### Affected tests
- unit: customer_unit
- integration: customer_integration
- contract: customer_contract
- e2e: customer_e2e

### Severity reasons
- Breaking impact reaches a core financial service

### Owners
- @analytics-team, @digital-team, @finance-team

### CI gate: pending_approval