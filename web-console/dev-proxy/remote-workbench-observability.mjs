import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_OBSERVABILITY_DIR = path.resolve(
  MODULE_DIR,
  '../../data/host-services/mobile-workbench-gateway',
);
const ACTIVE_LOG_FILENAME = 'access.current.ndjson';
const MAX_ARCHIVE_FILES = 4;
const MAX_LOG_FILE_BYTES = 2 * 1024 * 1024;
const DEFAULT_SUMMARY_WINDOW_MS = 60 * 60 * 1000;
const DEFAULT_AUDIT_LIMIT = 40;
const MAX_AUDIT_LIMIT = 200;
const LATENCY_BUCKETS = [
  { label: '<=250ms', upper_bound_ms: 250 },
  { label: '251-1000ms', upper_bound_ms: 1000 },
  { label: '1001-5000ms', upper_bound_ms: 5000 },
  { label: '5001-15000ms', upper_bound_ms: 15000 },
  { label: '>15000ms', upper_bound_ms: null },
];

function normalizeString(value = '') {
  return String(value || '').trim();
}

function normalizeIdentifier(value = '') {
  return normalizeString(value).toLowerCase();
}

function normalizeNullable(value = '') {
  const normalized = normalizeString(value);
  return normalized || null;
}

function normalizePathname(requestUrl = '/') {
  try {
    return new URL(requestUrl, 'http://localhost').pathname || '/';
  } catch {
    return String(requestUrl || '/').split('?')[0] || '/';
  }
}

function toInteger(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toFiniteNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function roundDuration(value = 0) {
  return Math.round(toFiniteNumber(value, 0) * 100) / 100;
}

function clampLimit(value, defaultValue = DEFAULT_AUDIT_LIMIT) {
  const parsed = toInteger(value, defaultValue);
  if (parsed < 1) {
    return 1;
  }
  if (parsed > MAX_AUDIT_LIMIT) {
    return MAX_AUDIT_LIMIT;
  }
  return parsed;
}

function archiveFilename(index) {
  return `access.${index}.ndjson`;
}

function resolveRequestHost(requestHeaders = {}) {
  const rawHost = normalizeString(requestHeaders?.host || requestHeaders?.Host || '');
  if (!rawHost) {
    return '';
  }
  try {
    return new URL(`http://${rawHost}`).hostname.toLowerCase();
  } catch {
    return '';
  }
}

function isLoopbackHostname(hostname = '') {
  const normalized = normalizeIdentifier(hostname);
  return normalized === 'localhost'
    || normalized.endsWith('.localhost')
    || normalized === '::1'
    || normalized === '0:0:0:0:0:0:0:1'
    || /^127(?:\.\d{1,3}){3}$/.test(normalized);
}

function resolvePublicHostname(publicOrigin = '') {
  const normalizedOrigin = normalizeString(publicOrigin);
  if (!normalizedOrigin) {
    return '';
  }
  try {
    return new URL(normalizedOrigin).hostname.toLowerCase();
  } catch {
    return '';
  }
}

function classifyOriginType(hostname = '', publicOrigin = '') {
  if (!hostname) {
    return 'unknown_host';
  }
  if (isLoopbackHostname(hostname)) {
    return 'loopback_host';
  }
  const publicHostname = resolvePublicHostname(publicOrigin);
  if (publicHostname && hostname === publicHostname) {
    return 'public_host';
  }
  return 'other_host';
}

function classifyRouteClass(context = {}, ingress = '') {
  const requestPath = normalizeString(context?.path || '/');
  if (normalizeIdentifier(ingress) === 'device_link_https') {
    return 'device_link';
  }
  if (/^\/api\/v1\/workspaces\/[^/]+\/device-bindings\//.test(requestPath)) {
    return 'device_link';
  }
  if (/^\/workspaces\/[^/]+\/capability-ui-hosts\/[^/]+(?:\/.*)?$/.test(requestPath)) {
    return 'host_page';
  }
  if (/^\/api\/v1\/capability-packs\/installed-capabilities\/[^/]+\/ui-assets\/.+/.test(requestPath)) {
    return 'ui_asset';
  }
  if (/^\/api\/v1\/workspaces\/[^/]+\/events\/stream$/.test(requestPath)) {
    return 'events_stream';
  }
  if (
    /^\/api\/v1\/ig(?:\/.*)?$/.test(requestPath)
    || /^\/api\/v1\/capabilities\/[^/]+(?:\/.*)?$/.test(requestPath)
  ) {
    return 'capability_api';
  }
  return 'workspace_support';
}

function mapCompletionOutcome(event = 'finish') {
  const normalized = normalizeIdentifier(event);
  if (normalized === 'upstream_error' || normalized === 'client_aborted' || normalized === 'client_closed') {
    return 'error';
  }
  return 'proxied';
}

function createLatencyBucketRows() {
  return LATENCY_BUCKETS.map((bucket) => ({
    label: bucket.label,
    upper_bound_ms: bucket.upper_bound_ms,
    count: 0,
  }));
}

function addDurationToLatencyBuckets(latencyBuckets, durationMs) {
  const duration = toFiniteNumber(durationMs, 0);
  const bucket = latencyBuckets.find((candidate) =>
    candidate.upper_bound_ms === null || duration <= candidate.upper_bound_ms);
  if (bucket) {
    bucket.count += 1;
  }
}

function computeAverage(values = []) {
  if (!values.length) {
    return null;
  }
  const total = values.reduce((sum, value) => sum + toFiniteNumber(value, 0), 0);
  return Math.round((total / values.length) * 100) / 100;
}

function computePercentile(values = [], percentile = 0.95) {
  if (!values.length) {
    return null;
  }
  const sorted = values
    .map((value) => toFiniteNumber(value, 0))
    .sort((left, right) => left - right);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.ceil(sorted.length * percentile) - 1));
  return Math.round(sorted[index] * 100) / 100;
}

function mapToSortedRows(map, projector, limit = 5) {
  return Array.from(map.values())
    .sort((left, right) => {
      const requestDelta = toInteger(right.requests, 0) - toInteger(left.requests, 0);
      if (requestDelta !== 0) {
        return requestDelta;
      }
      return toInteger(right.response_bytes, 0) - toInteger(left.response_bytes, 0);
    })
    .slice(0, limit)
    .map(projector);
}

function summarizeRouteClassRows(routeClassMap) {
  return Array.from(routeClassMap.values())
    .sort((left, right) => left.route_class.localeCompare(right.route_class))
    .map((row) => ({
      route_class: row.route_class,
      requests: row.requests,
      denied: row.denied,
      errors: row.errors,
      response_bytes: row.response_bytes,
      avg_duration_ms: computeAverage(row.duration_values),
    }));
}

function listStringValues(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeString(item))
      .filter(Boolean);
  }
  const normalized = normalizeString(value);
  return normalized ? [normalized] : [];
}

function isBrowserRunnerRecord(record = {}) {
  const runnerType = normalizeIdentifier(
    record.runner_type
    || record.profile_code
    || record?.resource_snapshot?.profile_code
    || record.runner_profile
    || record.profile
    || record.type,
  );
  const resourceClasses = listStringValues(
    record.resource_classes
    || record.classes
    || record.capabilities,
  ).map((item) => item.toLowerCase());
  const admissionReasons = listStringValues(record?.admission?.reasons).map((item) => item.toLowerCase());
  return runnerType.includes('browser')
    || resourceClasses.some((item) => item.includes('browser'))
    || admissionReasons.includes('browser_session_slots');
}

function summarizeRunnerSnapshot(rawSnapshot = null, collectedAt = new Date().toISOString()) {
  const runners = Array.isArray(rawSnapshot?.runners) ? rawSnapshot.runners : [];
  const browserRunners = runners
    .filter(isBrowserRunnerRecord)
    .map((runner) => ({
      runner_id: normalizeString(runner.runner_id || runner.id || 'unknown-runner'),
      runner_type: normalizeString(
        runner.runner_type
        || runner.profile_code
        || runner?.resource_snapshot?.profile_code
        || runner.runner_profile
        || runner.profile
        || runner.type
        || 'unknown',
      ),
      inflight: toInteger(runner.inflight ?? runner?.resource_snapshot?.inflight, 0),
      max_inflight: toInteger(runner.max_inflight ?? runner?.resource_snapshot?.max_inflight, 0),
      admission_state: normalizeNullable(
        runner?.admission?.state
        || runner?.resource_snapshot?.admission?.state
        || null,
      ),
      admission_reasons: listStringValues(
        runner?.admission?.reasons
        || runner?.resource_snapshot?.admission?.reasons,
      ),
    }));
  const softDeferReasons = Array.from(
    new Set(
      browserRunners
        .filter((runner) => normalizeIdentifier(runner.admission_state) === 'soft_defer')
        .flatMap((runner) => runner.admission_reasons),
    ),
  ).sort((left, right) => left.localeCompare(right));
  return {
    collected_at: collectedAt,
    browser_runners: browserRunners.length,
    inflight_total: browserRunners.reduce((sum, runner) => sum + runner.inflight, 0),
    max_inflight_total: browserRunners.reduce((sum, runner) => sum + runner.max_inflight, 0),
    soft_defer_count: browserRunners.filter(
      (runner) => normalizeIdentifier(runner.admission_state) === 'soft_defer',
    ).length,
    soft_defer_reasons: softDeferReasons,
    runners: browserRunners.slice(0, 8),
    source_status: normalizeNullable(rawSnapshot?.status || 'ok'),
  };
}

function matchesFilter(record, { workspaceId = null, capabilityCode = null, originType = 'public_host' } = {}) {
  const normalizedWorkspaceId = normalizeIdentifier(workspaceId || '');
  const normalizedCapabilityCode = normalizeIdentifier(capabilityCode || '');
  const normalizedOriginType = normalizeIdentifier(originType || 'public_host');
  if (normalizedOriginType && normalizedOriginType !== 'all') {
    if (normalizeIdentifier(record.origin_type) !== normalizedOriginType) {
      return false;
    }
  }
  if (normalizedWorkspaceId && normalizeIdentifier(record.workspace_id) !== normalizedWorkspaceId) {
    return false;
  }
  if (normalizedCapabilityCode && normalizeIdentifier(record.capability_code) !== normalizedCapabilityCode) {
    return false;
  }
  return true;
}

async function safeUnlink(filePath) {
  try {
    await fs.promises.rm(filePath, { force: true });
  } catch {
    // Best-effort cleanup only.
  }
}

async function safeRename(sourcePath, targetPath) {
  try {
    await fs.promises.rename(sourcePath, targetPath);
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      throw error;
    }
  }
}

export function createRemoteWorkbenchObservability({
  dataDir = DEFAULT_OBSERVABILITY_DIR,
  loadRunnerSnapshot = async () => null,
} = {}) {
  const baseDir = path.resolve(String(dataDir || DEFAULT_OBSERVABILITY_DIR));
  const activeLogPath = path.join(baseDir, ACTIVE_LOG_FILENAME);
  let appendChain = Promise.resolve();

  async function ensureBaseDir() {
    await fs.promises.mkdir(baseDir, { recursive: true });
  }

  async function rotateLogsIfNeeded(nextWriteBytes = 0) {
    await ensureBaseDir();
    let currentSize = 0;
    try {
      const stats = await fs.promises.stat(activeLogPath);
      currentSize = stats.size;
    } catch (error) {
      if (error?.code !== 'ENOENT') {
        throw error;
      }
    }
    if (currentSize + nextWriteBytes <= MAX_LOG_FILE_BYTES) {
      return;
    }
    await safeUnlink(path.join(baseDir, archiveFilename(MAX_ARCHIVE_FILES)));
    for (let index = MAX_ARCHIVE_FILES - 1; index >= 1; index -= 1) {
      await safeRename(
        path.join(baseDir, archiveFilename(index)),
        path.join(baseDir, archiveFilename(index + 1)),
      );
    }
    await safeRename(activeLogPath, path.join(baseDir, archiveFilename(1)));
  }

  async function flushWrites() {
    try {
      await appendChain;
    } catch {
      // Reads should stay available even when a prior append failed.
    }
  }

  function enqueueAppend(record) {
    const line = `${JSON.stringify(record)}\n`;
    const lineBytes = Buffer.byteLength(line);
    appendChain = appendChain
      .then(async () => {
        await rotateLogsIfNeeded(lineBytes);
        await ensureBaseDir();
        await fs.promises.appendFile(activeLogPath, line, 'utf8');
      })
      .catch((error) => {
        console.error('[remote-workbench-observability] append failed', error);
      });
    return appendChain;
  }

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

  async function readRawRecords() {
    await flushWrites();
    const candidateFiles = [
      activeLogPath,
      ...Array.from({ length: MAX_ARCHIVE_FILES }, (_, index) =>
        path.join(baseDir, archiveFilename(index + 1))),
    ];
    const records = [];
    for (const filePath of candidateFiles) {
      let fileContents = '';
      try {
        fileContents = await fs.promises.readFile(filePath, 'utf8');
      } catch (error) {
        if (error?.code === 'ENOENT') {
          continue;
        }
        throw error;
      }
      const lines = fileContents.split('\n').filter(Boolean);
      for (const line of lines) {
        try {
          const record = JSON.parse(line);
          if (record && typeof record === 'object') {
            records.push(record);
          }
        } catch {
          // Skip malformed lines and preserve read availability.
        }
      }
    }
    return records;
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

export {
  DEFAULT_AUDIT_LIMIT,
  DEFAULT_OBSERVABILITY_DIR,
  DEFAULT_SUMMARY_WINDOW_MS,
  LATENCY_BUCKETS,
  MAX_ARCHIVE_FILES,
  MAX_LOG_FILE_BYTES,
  MAX_AUDIT_LIMIT,
};
