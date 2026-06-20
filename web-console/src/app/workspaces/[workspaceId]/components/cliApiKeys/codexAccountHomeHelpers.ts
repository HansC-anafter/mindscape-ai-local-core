'use client';

import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock3,
  ShieldCheck,
  UserRound,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import type { AgentAuthActionResponse, CodexAccountHomeTarget } from './types';

export const CODEX_LOGIN_TIMEOUT_MS = 300_000;
export const CODEX_LOGOUT_TIMEOUT_MS = 45_000;
export const CODEX_PROBE_TIMEOUT_MS = 120_000;

export const CODEX_AUTH_ERROR_CODES = new Set([
  '401',
  '403',
  'auth_failure',
  'deactivated_workspace',
  'missing_refresh_token',
  'stale_refresh_token',
  'unauthorized',
]);

export const CODEX_QUOTA_ERROR_CODES = new Set([
  '429',
  'quota',
  'rate_limit',
  'resource_exhausted',
]);

export const CODEX_INCONCLUSIVE_ERROR_CODES = new Set([
  'timeout',
  'runtime_error',
  'probe_transport_error',
  'codex_cli_panic',
  'token_refresh_persist_failed',
]);

export type CodexStatusMeta = {
  label: string;
  detail: string;
  icon: LucideIcon;
  badge: string;
  row: string;
};

export type CodexScopeMeta = {
  label: string;
  sublabel: string;
  icon: LucideIcon;
  badge: string;
};

export const fetchWithTimeout = async (
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number
) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
};

export const isAbortError = (value: unknown) =>
  value instanceof Error && value.name === 'AbortError';

export const normalizedCode = (value: string | null | undefined) =>
  (value || '').trim().toLowerCase();

export const errorMessageFromPayload = (
  payload: unknown,
  fallback: string
) => {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    const detail = record.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const error = record.error;
    if (typeof error === 'string' && error.trim()) return error;
    const note = record.note;
    if (typeof note === 'string' && note.trim()) return note;
  }
  return fallback;
};

export const probeErrorCodeFromPayload = (payload: AgentAuthActionResponse) => {
  const direct = normalizedCode(payload.error);
  if (direct) return direct;
  if (!payload.output) return '';
  try {
    const parsed = JSON.parse(payload.output) as Record<string, unknown>;
    return normalizedCode(
      typeof parsed.error_code === 'string'
        ? parsed.error_code
        : typeof parsed.error === 'string'
          ? parsed.error
          : ''
    );
  } catch {
    return '';
  }
};

export const codexAccountHomesRoot = (targets: CodexAccountHomeTarget[]) => {
  const home = targets.find((target) => target.codex_home)?.codex_home || '';
  const marker = '/accounts/';
  const markerIndex = home.indexOf(marker);
  if (markerIndex >= 0) {
    return home.slice(0, markerIndex + marker.length - 1);
  }
  return '/Users/shock/.mindscape/runtime/codex-home-pool/accounts';
};

export const newCodexAccountHomePath = (targets: CodexAccountHomeTarget[]) => {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 8)}`;
  return `${codexAccountHomesRoot(targets)}/acct-${suffix}`;
};

export const shortRuntimeId = (value: string | null | undefined) => {
  const raw = value || '';
  return raw.replace(/^runtime-codex_cli-/, 'codex:');
};

export const shortKey = (value: string | null | undefined) => {
  const raw = value || '';
  return raw.length > 14 ? `${raw.slice(0, 8)}...${raw.slice(-6)}` : raw;
};

export const codexStatusMeta = (target: CodexAccountHomeTarget): CodexStatusMeta => {
  const errorCode = normalizedCode(target.last_probe_error_code || target.last_error_code);
  if (target.probe_state === 'available') {
    return {
      label: 'Available',
      detail: 'Token refresh passed',
      icon: CheckCircle2,
      badge: 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300',
      row: 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10',
    };
  }
  if (target.probe_state === 'quota_limited' || CODEX_QUOTA_ERROR_CODES.has(errorCode)) {
    return {
      label: 'Quota limited',
      detail: errorCode || '429',
      icon: Clock3,
      badge: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300',
      row: 'border-amber-200 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-900/10',
    };
  }
  if (target.probe_state === 'probe_inconclusive' || CODEX_INCONCLUSIVE_ERROR_CODES.has(errorCode)) {
    return {
      label: 'Probe inconclusive',
      detail: errorCode || 'runtime check interrupted',
      icon: AlertTriangle,
      badge: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-300',
      row: 'border-slate-200 dark:border-slate-700 bg-slate-50/40 dark:bg-slate-900/10',
    };
  }
  if (target.probe_state === 'auth_failed' || CODEX_AUTH_ERROR_CODES.has(errorCode)) {
    return {
      label: 'Auth failed',
      detail: errorCode || 'auth_failed',
      icon: XCircle,
      badge: 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300',
      row: 'border-red-200 dark:border-red-800 bg-red-50/40 dark:bg-red-900/10',
    };
  }
  if (target.probe_state === 'runtime_failed' || errorCode) {
    return {
      label: 'Runtime failed',
      detail: errorCode || 'runtime_error',
      icon: AlertTriangle,
      badge: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-300',
      row: 'border-slate-200 dark:border-slate-700 bg-slate-50/40 dark:bg-slate-900/10',
    };
  }
  return {
    label: 'Unknown',
    detail: 'Probe required',
    icon: AlertTriangle,
    badge: 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900/30 dark:text-gray-300',
    row: 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
  };
};

export const codexScopeMeta = (target: CodexAccountHomeTarget): CodexScopeMeta => {
  const scopeType = (target.account_scope_type || '').toLowerCase();
  if (scopeType === 'personal') {
    return {
      label: target.account_scope_label || 'Personal',
      sublabel: target.account_plan_type || 'personal',
      icon: UserRound,
      badge: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-300',
    };
  }
  if (scopeType === 'workspace') {
    return {
      label: target.account_scope_label || target.account_organization_title || 'Workspace',
      sublabel: [target.account_scope_role, target.account_plan_type].filter(Boolean).join(' / ') || 'workspace',
      icon: Building2,
      badge: 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-300',
    };
  }
  return {
    label: 'Unknown scope',
    sublabel: target.account_plan_type || 'unclassified',
    icon: ShieldCheck,
    badge: 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900/30 dark:text-gray-300',
  };
};
