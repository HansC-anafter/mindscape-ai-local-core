import {
  isCapabilityOwnedApiPrefix,
} from '../mobile-workbench-gateway-capability-rules.mjs';

const MAX_API_PREFIXES = 32;
const MAX_COMPONENT_CODES = 128;
const REQUEST_SCOPE_CONTRACTS = new Set([
  'explicit_workspace_v1',
  'no_remote_requests_v1',
]);

function malformed(reason) {
  throw new Error(`mobile_workbench_policy_malformed:${reason}`);
}

function boundedString(value, maxLength, reason) {
  if (typeof value !== 'string') malformed(reason);
  const normalized = value.trim();
  if (!normalized || normalized.length > maxLength || /[\u0000-\u001f\u007f]/.test(normalized)) {
    malformed(reason);
  }
  return normalized;
}

export function normalizeCapabilitySupport(payload, expectedCapabilityCode) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    malformed('invalid_capability_support');
  }
  const capabilityCode = boundedString(
    payload.capability_code,
    128,
    'invalid_capability_support_code',
  ).toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(capabilityCode) || capabilityCode !== expectedCapabilityCode) {
    malformed('capability_support_identity_mismatch');
  }
  if (typeof payload.supported !== 'boolean') malformed('invalid_capability_support_flag');
  if (typeof payload.has_ui_components !== 'boolean') {
    malformed('invalid_capability_ui_components_flag');
  }
  const requestScopeContract = payload.request_scope_contract === null
    ? null
    : boundedString(payload.request_scope_contract, 64, 'invalid_request_scope_contract');
  if (requestScopeContract !== null && !REQUEST_SCOPE_CONTRACTS.has(requestScopeContract)) {
    malformed('invalid_request_scope_contract');
  }
  if (!Array.isArray(payload.main_page_component_codes)
    || payload.main_page_component_codes.length > MAX_COMPONENT_CODES) {
    malformed('invalid_main_page_component_codes');
  }
  const mainPageComponentCodes = Array.from(new Set(
    payload.main_page_component_codes.map((value) => (
      boundedString(value, 128, 'invalid_main_page_component_code')
    )),
  ));
  if (mainPageComponentCodes.length !== payload.main_page_component_codes.length) {
    malformed('duplicate_main_page_component_code');
  }
  if (!Array.isArray(payload.api_prefixes) || payload.api_prefixes.length > MAX_API_PREFIXES) {
    malformed('invalid_capability_api_prefixes');
  }
  const apiPrefixes = Array.from(new Set(payload.api_prefixes.map((value) => {
    const prefix = boundedString(value, 256, 'invalid_capability_api_prefix').replace(/\/+$/, '');
    if (!isCapabilityOwnedApiPrefix(prefix, capabilityCode)) {
      malformed('unowned_capability_api_prefix');
    }
    return prefix;
  })));
  if (apiPrefixes.length !== payload.api_prefixes.length) {
    malformed('duplicate_capability_api_prefix');
  }
  const hostRouteTemplate = payload.host_route_template === null
    ? null
    : boundedString(payload.host_route_template, 512, 'invalid_host_route_template');
  const canonical = `/workspaces/{workspaceId}/capability-ui-hosts/${capabilityCode}`;
  if (hostRouteTemplate !== null && hostRouteTemplate !== canonical) {
    malformed('noncanonical_host_route_template');
  }
  const projectedSupport = payload.has_ui_components
    && mainPageComponentCodes.length > 0
    && hostRouteTemplate === canonical
    && REQUEST_SCOPE_CONTRACTS.has(requestScopeContract);
  if (payload.supported !== projectedSupport
    || (!payload.has_ui_components && mainPageComponentCodes.length > 0)) {
    malformed('capability_support_projection_mismatch');
  }
  return {
    capabilityCode,
    supported: payload.supported,
    hasUiComponents: payload.has_ui_components,
    hostRouteTemplate,
    mainPageComponentCodes,
    requestScopeContract,
    apiPrefixes,
  };
}
