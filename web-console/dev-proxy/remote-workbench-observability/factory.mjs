import path from 'node:path';

import {
  ACTIVE_LOG_FILENAME,
  DEFAULT_AUDIT_LIMIT,
  DEFAULT_OBSERVABILITY_DIR,
  DEFAULT_SUMMARY_WINDOW_MS,
} from './constants.mjs';
import {
  classifyOriginType,
  classifyRouteClass,
  mapCompletionOutcome,
  matchesFilter,
  resolveRequestHost,
  summarizeRunnerSnapshot,
} from './classification.mjs';
import {
  addDurationToLatencyBuckets,
  computeAverage,
  computePercentile,
  createLatencyBucketRows,
  mapToSortedRows,
  summarizeRouteClassRows,
} from './metrics.mjs';
import {
  clampLimit,
  normalizeIdentifier,
  normalizeNullable,
  normalizePathname,
  normalizeString,
  roundDuration,
  toFiniteNumber,
  toInteger,
} from './normalizers.mjs';
import {
  createRemoteWorkbenchLogStore,
} from './storage.mjs';

export function createRemoteWorkbenchObservability({
  dataDir = DEFAULT_OBSERVABILITY_DIR,
  loadRunnerSnapshot = async () => null,
} = {}) {
  const baseDir = path.resolve(String(dataDir || DEFAULT_OBSERVABILITY_DIR));
  const activeLogPath = path.join(baseDir, ACTIVE_LOG_FILENAME);
  const { enqueueAppend, readRawRecords } = createRemoteWorkbenchLogStore({
    baseDir,
    activeLogPath,
  });

  function createObservation({
    requestId,
    requestUrl = '/',
    requestMethod = 'GET',
    requestHeaders = {},
    requestResult = {},
    mobileWorkbenchGatewayConfig = {},
  }) {
    const context = requestResult?.context || {};
    const host = resolveRequestHost(requestHeaders);
    return {
      timestamp: new Date().toISOString(),
      request_id: String(requestId),
      method: normalizeString(requestMethod || 'GET').toUpperCase() || 'GET',
      path: normalizeString(context.path || normalizePathname(requestUrl) || '/'),
      host: host || null,
      origin_type: classifyOriginType(host, mobileWorkbenchGatewayConfig?.publicOrigin),
      ingress: normalizeNullable(requestResult?.ingress || 'remote_gateway'),
      route_class: classifyRouteClass(context, requestResult?.ingress),
      workspace_id: normalizeNullable(context.workspaceId),
      capability_code: normalizeNullable(context.capabilityCode),
    };
  }

  function recordDeniedRequest(observation, {
    requestResult = {},
    statusCode = 404,
    responseBytes = 0,
  } = {}) {
    if (!observation) {
      return Promise.resolve();
    }
    return enqueueAppend({
      ...observation,
      outcome: 'denied',
      reason_code: normalizeNullable(requestResult?.reason_code || requestResult?.reason || null),
      status_code: toInteger(statusCode, 404),
      duration_ms: 0,
      response_bytes: toInteger(responseBytes, 0),
      upstream_kind: null,
      upstream_status: null,
      upstream_header_ms: null,
      proxy_event: 'denied',
      error: null,
    });
  }

  function recordCompletedRequest(observation, {
    event = 'finish',
    statusCode = 200,
    responseBytes = 0,
    durationMs = 0,
    upstreamKind = null,
    upstreamStatus = null,
    upstreamHeaderMs = null,
    error = null,
  } = {}) {
    if (!observation) {
      return Promise.resolve();
    }
    return enqueueAppend({
      ...observation,
      outcome: mapCompletionOutcome(event),
      reason_code: null,
      status_code: toInteger(statusCode, 200),
      duration_ms: roundDuration(durationMs),
      response_bytes: toInteger(responseBytes, 0),
      upstream_kind: normalizeNullable(upstreamKind),
      upstream_status: upstreamStatus === null ? null : toInteger(upstreamStatus, 0),
      upstream_header_ms: upstreamHeaderMs === null ? null : roundDuration(upstreamHeaderMs),
      proxy_event: normalizeNullable(event),
      error: normalizeNullable(error),
    });
  }

  async function readSummary({
    workspaceId = null,
    capabilityCode = null,
    originType = 'public_host',
    windowMs = DEFAULT_SUMMARY_WINDOW_MS,
  } = {}) {
    const generatedAt = new Date().toISOString();
    const summaryWindowMs = Math.max(1, toInteger(windowMs, DEFAULT_SUMMARY_WINDOW_MS));
    const cutoffEpochMs = Date.now() - summaryWindowMs;
    const allRecords = await readRawRecords();
    const filteredRecords = allRecords.filter((record) => {
      if (!matchesFilter(record, { workspaceId, capabilityCode, originType })) {
        return false;
      }
      const eventEpochMs = Date.parse(record.timestamp || '');
      if (!Number.isFinite(eventEpochMs)) {
        return false;
      }
      return eventEpochMs >= cutoffEpochMs;
    });

    const latencyBuckets = createLatencyBucketRows();
    const durationValues = [];
    const routeClassMap = new Map();
    const workspaceMap = new Map();
    const capabilityMap = new Map();
    let proxiedCount = 0;
    let deniedCount = 0;
    let errorCount = 0;
    let responseBytes = 0;
    let slowOver1000Ms = 0;

    for (const record of filteredRecords) {
      const durationMs = toFiniteNumber(record.duration_ms, 0);
      const bytes = toInteger(record.response_bytes, 0);
      const routeClass = normalizeString(record.route_class || 'workspace_support') || 'workspace_support';
      const outcome = normalizeIdentifier(record.outcome);
      durationValues.push(durationMs);
      addDurationToLatencyBuckets(latencyBuckets, durationMs);
      responseBytes += bytes;
      if (durationMs > 1000) {
        slowOver1000Ms += 1;
      }
      if (outcome === 'proxied') {
        proxiedCount += 1;
      } else if (outcome === 'denied') {
        deniedCount += 1;
      } else {
        errorCount += 1;
      }

      const routeRow = routeClassMap.get(routeClass) || {
        route_class: routeClass,
        requests: 0,
        denied: 0,
        errors: 0,
        response_bytes: 0,
        duration_values: [],
      };
      routeRow.requests += 1;
      routeRow.response_bytes += bytes;
      routeRow.duration_values.push(durationMs);
      if (outcome === 'denied') {
        routeRow.denied += 1;
      } else if (outcome === 'error') {
        routeRow.errors += 1;
      }
      routeClassMap.set(routeClass, routeRow);

      const workspaceKey = normalizeIdentifier(record.workspace_id || '');
      if (workspaceKey) {
        const workspaceRow = workspaceMap.get(workspaceKey) || {
          workspace_id: normalizeString(record.workspace_id),
          requests: 0,
          denied: 0,
          response_bytes: 0,
        };
        workspaceRow.requests += 1;
        workspaceRow.response_bytes += bytes;
        if (outcome === 'denied') {
          workspaceRow.denied += 1;
        }
        workspaceMap.set(workspaceKey, workspaceRow);
      }

      const capabilityKey = normalizeIdentifier(record.capability_code || '');
      if (capabilityKey) {
        const capabilityRow = capabilityMap.get(capabilityKey) || {
          capability_code: normalizeString(record.capability_code),
          requests: 0,
          denied: 0,
          response_bytes: 0,
        };
        capabilityRow.requests += 1;
        capabilityRow.response_bytes += bytes;
        if (outcome === 'denied') {
          capabilityRow.denied += 1;
        }
        capabilityMap.set(capabilityKey, capabilityRow);
      }
    }

    let runnerSnapshot;
    try {
      const rawSnapshot = await loadRunnerSnapshot();
      runnerSnapshot = summarizeRunnerSnapshot(rawSnapshot, generatedAt);
    } catch (error) {
      runnerSnapshot = {
        collected_at: generatedAt,
        browser_runners: 0,
        inflight_total: 0,
        max_inflight_total: 0,
        soft_defer_count: 0,
        soft_defer_reasons: [],
        runners: [],
        source_status: 'error',
        error: error instanceof Error ? error.message : 'runner_snapshot_unavailable',
      };
    }

    return {
      service: 'mobile-workbench-gateway',
      generated_at: generatedAt,
      summary_window_minutes: Math.round(summaryWindowMs / 60000),
      origin_filter: normalizeIdentifier(originType || 'public_host') || 'public_host',
      filters: {
        workspace_id: normalizeNullable(workspaceId),
        capability_code: normalizeNullable(capabilityCode),
      },
      request_totals: {
        total: filteredRecords.length,
        proxied: proxiedCount,
        denied: deniedCount,
        errors: errorCount,
        response_bytes: responseBytes,
        avg_duration_ms: computeAverage(durationValues),
        p95_duration_ms: computePercentile(durationValues, 0.95),
        slow_over_1000ms: slowOver1000Ms,
      },
      latency_buckets: latencyBuckets,
      by_route_class: summarizeRouteClassRows(routeClassMap),
      top_workspaces: mapToSortedRows(workspaceMap, (row) => row),
      top_capabilities: mapToSortedRows(capabilityMap, (row) => row),
      runner_snapshot: runnerSnapshot,
    };
  }

  async function readAuditTail({
    workspaceId = null,
    capabilityCode = null,
    originType = 'public_host',
    limit = DEFAULT_AUDIT_LIMIT,
  } = {}) {
    const generatedAt = new Date().toISOString();
    const boundedLimit = clampLimit(limit, DEFAULT_AUDIT_LIMIT);
    const filteredRecords = (await readRawRecords())
      .filter((record) => matchesFilter(record, { workspaceId, capabilityCode, originType }))
      .sort((left, right) =>
        Date.parse(right.timestamp || '1970-01-01T00:00:00Z')
        - Date.parse(left.timestamp || '1970-01-01T00:00:00Z'))
      .slice(0, boundedLimit);
    return {
      service: 'mobile-workbench-gateway',
      generated_at: generatedAt,
      origin_filter: normalizeIdentifier(originType || 'public_host') || 'public_host',
      filters: {
        workspace_id: normalizeNullable(workspaceId),
        capability_code: normalizeNullable(capabilityCode),
        limit: boundedLimit,
      },
      events: filteredRecords,
    };
  }

  return {
    dataDir: baseDir,
    recordDeniedRequest,
    recordCompletedRequest,
    readSummary,
    readAuditTail,
    createObservation,
  };
}
