# 快速開始指南

## 1. 啟動監控服務

```bash
cd mindscape-ai-local-core

# 啟動核心監控服務（常駐）
docker compose -f docker-compose.monitoring.yml up -d prometheus victoria-metrics alertmanager node-exporter

# 檢查狀態
docker compose -f docker-compose.monitoring.yml ps
```

## 2. 驗證 Backend Metrics

```bash
# 檢查 backend metrics 端點
curl http://localhost:8200/metrics | grep runtime_profile

# 應該看到類似：
# runtime_profile_policy_check_total{...}
# runtime_profile_budget_exhausted_total{...}
# runtime_profile_quality_gate_check_total{...}
```

## 3. 檢查 Prometheus Targets

訪問 http://localhost:9090/targets

應該看到 `mindscape-backend` target 狀態為 "UP"。

如果狀態為 "DOWN"：
- 確認 backend 容器正在運行：`docker compose ps backend`
- 確認網絡連接：兩個容器應該在同一個 `mindscape-network` 網絡中
- 檢查 Prometheus 配置中的 target 地址

## 4. 啟動 Grafana（按需）

```bash
docker compose -f docker-compose.monitoring.yml up -d grafana
```

訪問 http://localhost:3000
- 用戶名：`admin`
- 密碼：`changeme`

## 5. 創建第一個儀表板

1. 登入 Grafana
2. 點擊 "Dashboards" → "New Dashboard"
3. 點擊 "Add visualization"
4. 選擇 "Prometheus" 數據源
5. 輸入查詢：`sum(rate(runtime_profile_policy_check_total[5m])) by (tool_id)`
6. 點擊 "Run query"

## 6. 停止 Grafana（節省資源）

```bash
docker compose -f docker-compose.monitoring.yml stop grafana
```

---

## 故障排除

### Prometheus 無法連接 Backend

**檢查網絡**：
```bash
# 檢查 backend 容器網絡
docker inspect mindscape-ai-local-core-backend | grep -A 10 Networks

# 檢查 Prometheus 容器網絡
docker inspect mindscape-local-core-prometheus | grep -A 10 Networks

# 應該都在 mindscape-network 中
```

**測試連接**：
```bash
# 從 Prometheus 容器測試 backend 連接
docker exec mindscape-local-core-prometheus wget -O- http://mindscape-ai-local-core-backend:8200/metrics
```

**修正方案**：
如果網絡不匹配，可以：
1. 使用 `docker network connect mindscape-network mindscape-local-core-prometheus`
2. 或者修改 `docker-compose.monitoring.yml` 使用正確的網絡名稱

---

## 常用命令

```bash
# 查看所有監控容器狀態
docker compose -f docker-compose.monitoring.yml ps

# 查看 Prometheus 日誌
docker compose -f docker-compose.monitoring.yml logs prometheus

# 查看 Grafana 日誌
docker compose -f docker-compose.monitoring.yml logs grafana

# 重啟 Prometheus
docker compose -f docker-compose.monitoring.yml restart prometheus

# 停止所有監控服務
docker compose -f docker-compose.monitoring.yml down

# 停止並刪除數據卷（注意：會刪除所有歷史數據）
docker compose -f docker-compose.monitoring.yml down -v
```

