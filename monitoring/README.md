# Mindscape AI Local-Core Monitoring Setup

## Overview

This directory contains monitoring configuration for Mindscape AI Local-Core using Prometheus, VictoriaMetrics, Grafana, and Alertmanager.

**Important**: All monitoring runs locally (no GCP dependencies, no cloud costs).

## Quick Start

### 1. Start Core Monitoring Services

```bash
cd /path/to/mindscape-ai-local-core
docker compose -f docker-compose.monitoring.yml up -d prometheus victoria-metrics alertmanager node-exporter
```

### 2. Start Grafana (On-Demand)

```bash
docker compose -f docker-compose.monitoring.yml up -d grafana
```

Access Grafana at: http://localhost:3000
- Username: `admin`
- Password: `changeme` (or set `GRAFANA_ADMIN_PASSWORD` environment variable)

### 3. Stop Grafana (Save Resources)

```bash
docker compose -f docker-compose.monitoring.yml stop grafana
```

## Services

### Prometheus
- **Port**: 9090
- **URL**: http://localhost:9090
- **Purpose**: Scrapes metrics from backend API and node exporter
- **Retention**: 7 days

### VictoriaMetrics
- **Port**: 8428
- **URL**: http://localhost:8428
- **Purpose**: Long-term storage (90 days)
- **Note**: Prometheus can remote-write to VictoriaMetrics for long-term storage

### Grafana
- **Port**: 3000
- **URL**: http://localhost:3000
- **Purpose**: Visualization dashboards
- **Note**: Can be stopped when not needed

### Alertmanager
- **Port**: 9093
- **URL**: http://localhost:9093
- **Purpose**: Alert routing and notification
- **Note**: Currently configured for local-only (no external notifications)

### Node Exporter
- **Port**: 9100
- **URL**: http://localhost:9100/metrics
- **Purpose**: System metrics (CPU, memory, disk, etc.)

## Configuration Files

- `prometheus.yml` - Prometheus scrape configuration
- `prometheus-recording-rules.yml` - Pre-computed metrics
- `alertmanager.yml` - Alert routing configuration
- `grafana-provisioning/` - Grafana datasources and dashboards

## Metrics Available

### Runtime Profile Metrics

- `runtime_profile_policy_check_total` - PolicyGuard check count
- `runtime_profile_policy_check_denial_reasons_total` - Denial reasons
- `runtime_profile_budget_exhausted_total` - Budget exhaustion events
- `runtime_profile_budget_usage_percentage` - Budget usage percentage
- `runtime_profile_quality_gate_check_total` - Quality gate check count
- `runtime_profile_quality_gate_check_duration_seconds` - Quality gate check duration

### System Metrics

- `node_*` - System metrics from node exporter

## Creating Dashboards

1. Access Grafana: http://localhost:3000
2. Go to Dashboards → New Dashboard
3. Add panels with Prometheus queries (see examples below)

### Example Queries

**PolicyGuard Tool Call Rate**:
```
sum(rate(runtime_profile_policy_check_total[5m])) by (tool_id)
```

**Policy Denial Rate**:
```
sum(rate(runtime_profile_policy_check_total{allowed="false"}[5m]))
/
sum(rate(runtime_profile_policy_check_total[5m]))
```

**Budget Usage Percentage**:
```
runtime_profile_budget_usage_percentage
```

**Quality Gate Pass Rate**:
```
sum(rate(runtime_profile_quality_gate_check_total{passed="true"}[5m]))
/
sum(rate(runtime_profile_quality_gate_check_total[5m]))
```

## Alert Rules (Optional)

Add alert rules to `prometheus-recording-rules.yml` or create separate alert rules file:

```yaml
groups:
  - name: runtime_profile_alerts
    interval: 30s
    rules:
      - alert: RuntimeProfileBudgetExhausted
        expr: rate(runtime_profile_budget_exhausted_total[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Budget exhausted in workspace {{ $labels.workspace_id }}"

      - alert: RuntimeProfilePolicyDenialRateHigh
        expr: |
          sum(rate(runtime_profile_policy_check_total{allowed="false"}[5m]))
          /
          sum(rate(runtime_profile_policy_check_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Policy denial rate > 10% in workspace {{ $labels.workspace_id }}"
```

## Troubleshooting

### Prometheus Cannot Scrape Backend

1. Check if backend is running: `docker compose ps backend`
2. Check if backend is on the same network: `docker network inspect mindscape-network`
3. Test metrics endpoint: `curl http://localhost:8200/metrics`

### Grafana Cannot Connect to Prometheus

1. Check Prometheus is running: `docker compose ps prometheus`
2. Check Prometheus URL in Grafana datasource: `http://prometheus:9090`
3. Verify network connectivity: `docker exec mindscape-local-core-grafana ping prometheus`

### High Resource Usage

1. Stop Grafana when not needed: `docker compose stop grafana`
2. Reduce scrape interval in `prometheus.yml`
3. Reduce retention period in `docker-compose.monitoring.yml`

## Cost Optimization

- **Grafana**: Stop when not needed (saves ~512MB RAM)
- **VictoriaMetrics**: Can be stopped if only need 7-day retention
- **Node Exporter**: Can be stopped if not monitoring system metrics

## Security Notes

- All services run on local network (not exposed to internet)
- Grafana admin password should be changed in production
- Consider adding authentication for production use

