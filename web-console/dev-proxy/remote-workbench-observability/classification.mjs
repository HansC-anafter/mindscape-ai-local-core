import {
  listStringValues,
  normalizeIdentifier,
  normalizeNullable,
  normalizeString,
  toInteger,
} from './normalizers.mjs';

export function resolveRequestHost(requestHeaders = {}) {
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

export function classifyOriginType(hostname = '', publicOrigin = '') {
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

export function classifyRouteClass(context = {}, ingress = '') {
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

export function mapCompletionOutcome(event = 'finish') {
  const normalized = normalizeIdentifier(event);
  if (normalized === 'upstream_error' || normalized === 'client_aborted' || normalized === 'client_closed') {
    return 'error';
  }
  return 'proxied';
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

export function summarizeRunnerSnapshot(rawSnapshot = null, collectedAt = new Date().toISOString()) {
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

export function matchesFilter(record, { workspaceId = null, capabilityCode = null, originType = 'public_host' } = {}) {
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
