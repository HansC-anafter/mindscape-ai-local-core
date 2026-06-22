'use client';

export const PACK_SCOPE_TOOL_OPEN_EVENT = 'mindscape:pack-scope-tool-open';
export const PACK_SCOPE_TOOL_CLOSE_EVENT = 'mindscape:pack-scope-tool-close';

export interface PackScopeToolOpenDetail {
  capabilityCode?: string;
  toolId?: string;
  toolKey?: string;
}

export interface PackScopeToolCloseDetail {
  capabilityCode?: string;
  toolId?: string;
  toolKey?: string;
}

export function requestPackScopeToolOpen(detail: PackScopeToolOpenDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent<PackScopeToolOpenDetail>(PACK_SCOPE_TOOL_OPEN_EVENT, {
    detail,
  }));
}

export function requestPackScopeToolClose(detail: PackScopeToolCloseDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent<PackScopeToolCloseDetail>(PACK_SCOPE_TOOL_CLOSE_EVENT, {
    detail,
  }));
}
