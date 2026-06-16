'use client';

export const PACK_SCOPE_TOOL_OPEN_EVENT = 'mindscape:pack-scope-tool-open';

export interface PackScopeToolOpenDetail {
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
