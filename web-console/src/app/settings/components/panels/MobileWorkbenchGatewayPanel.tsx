'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw.js';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check.js';

import { useT } from '../../../../lib/i18n';
import { getApiBaseUrl } from '../../../../lib/api-url';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { Section } from '../Section';
import { StatusPill } from '../StatusPill';

interface GatewayConfigSummary {
  enabled?: boolean;
  reason?: string;
  errors?: string[];
  public_origin?: string | null;
  auth_config_source?: string | null;
  auth_config_fingerprint?: string | null;
  remote_access_state?: string | null;
  runtime_policy_revision?: number | null;
  startup_config_get_count?: number;
  remote_listener_ready?: boolean;
  jwt_signature_verification_required?: boolean;
  jwt_issuer_ready?: boolean;
  jwt_audience_ready?: boolean;
  effective_policy_cache_entries?: number;
  capability_support_cache_entries?: number;
  upstream_effective_policy_calls?: number;
  upstream_capability_support_calls?: number;
  upstream_in_flight?: number;
  upstream_rejected?: number;
  max_upstream_in_flight?: number;
}

interface MobileWorkbenchGatewayHealth {
  status?: string;
  service?: string;
  enabled?: boolean;
  reason?: string;
  errors?: string[];
  gateway?: GatewayConfigSummary;
}

const HEALTH_PATH = '/api/v1/host/services/mobile-workbench-gateway/health';
const REQUEST_TIMEOUT_MS = 10_000;

function isGatewayHealthPayload(value: unknown): value is MobileWorkbenchGatewayHealth {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const payload = value as Record<string, unknown>;
  return typeof payload.status === 'string'
    && typeof payload.enabled === 'boolean'
    && (payload.gateway === undefined || Boolean(payload.gateway && typeof payload.gateway === 'object'));
}

function display(value: string | number | boolean | null | undefined): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return value === null || value === undefined || value === '' ? '-' : String(value);
}

export function MobileWorkbenchGatewayPanel() {
  const t = useT();
  const [health, setHealth] = useState<MobileWorkbenchGatewayHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const apiBaseUrl = getApiBaseUrl().replace(/\/+$/, '');

  const loadHealth = useCallback(async () => {
    const requestGeneration = ++requestGenerationRef.current;
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    const isCurrentRequest = () => (
      mountedRef.current && requestGenerationRef.current === requestGeneration
    );
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}${HEALTH_PATH}`, {
        cache: 'no-store',
        signal: controller.signal,
      });
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        throw new Error('Remote Workbench gateway returned malformed JSON');
      }
      if (timedOut || controller.signal.aborted) {
        throw new DOMException('aborted', 'AbortError');
      }
      if (!isGatewayHealthPayload(payload)) {
        throw new Error('Remote Workbench gateway returned a malformed health payload');
      }
      const expectedBlockedResponse = response.status === 503 && payload.status === 'blocked';
      if (!response.ok && !expectedBlockedResponse) {
        throw new Error(`Remote Workbench gateway health request failed (${response.status})`);
      }
      if (isCurrentRequest()) {
        setHealth(payload);
      }
    } catch (requestError) {
      if (isCurrentRequest()) {
        setHealth(null);
        setError(
          timedOut
            ? 'Remote Workbench gateway health request timed out after 10 seconds'
            : requestError instanceof Error
              ? requestError.message
              : 'Failed to load Remote Workbench gateway status',
        );
      }
    } finally {
      window.clearTimeout(timeoutId);
      if (isCurrentRequest()) {
        activeControllerRef.current = null;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    mountedRef.current = true;
    void loadHealth();
    return () => {
      mountedRef.current = false;
      requestGenerationRef.current += 1;
      activeControllerRef.current?.abort();
      activeControllerRef.current = null;
    };
  }, [loadHealth]);

  const summary = health?.gateway;
  const healthErrors = [...(health?.errors || []), ...(summary?.errors || [])];
  const strictReady = Boolean(
    health?.status === 'ok'
    && health.enabled === true
    && summary?.enabled === true
    && summary?.remote_listener_ready
    && summary?.jwt_signature_verification_required
    && summary?.jwt_issuer_ready
    && summary?.jwt_audience_ready
    && summary?.auth_config_source === 'runtime_policy'
    && summary?.startup_config_get_count === 1
    && healthErrors.length === 0
  );
  const status = useMemo(() => {
    if (!health) return { status: 'unavailable' as const, label: 'Unavailable' };
    if (health.status === 'blocked') return { status: 'unavailable' as const, label: 'Blocked' };
    if (health.status === 'disabled' || health.enabled === false) return { status: 'disabled' as const, label: 'Disabled' };
    return strictReady
      ? { status: 'enabled' as const, label: 'Strict policy ready' }
      : { status: 'unavailable' as const, label: 'Blocked' };
  }, [health, strictReady]);

  return (
    <Section
      title="Remote Workbench Gateway Diagnostics"
      description="Read-only runtime health. Access policy changes have one dedicated Core Settings owner."
      headerRight={(
        <button
          type="button"
          onClick={() => {
            setRefreshing(true);
            void loadHealth();
          }}
          className="inline-flex items-center gap-2 rounded-md border border-default px-3 py-2 text-sm font-medium text-secondary hover:bg-surface-accent dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          aria-label="Refresh remote workbench gateway status"
        >
          <RefreshCw className={refreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          <span>{t('refresh' as any) || 'Refresh'}</span>
        </button>
      )}
    >
      {loading ? <div role="status" aria-live="polite" className="p-4 text-sm text-secondary">{t('loading' as any) || 'Loading...'}</div> : null}
      {error ? (
        <div role="alert">
          <InlineAlert type="error" title="Remote Workbench Gateway" description={error} />
        </div>
      ) : null}

      {!loading && health ? (
        <div className="space-y-4">
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-primary dark:text-gray-100">Gateway readiness</h3>
                  <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                </div>
                <p className="mt-1 text-sm text-secondary dark:text-gray-400">{health.service || 'mobile-workbench-gateway'}</p>
              </div>
              <StatusPill status={status.status} label={status.label} icon="" />
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {[
                ['Health', health.status],
                ['Remote access state', summary?.remote_access_state],
                ['Policy revision', summary?.runtime_policy_revision],
                ['Policy source', summary?.auth_config_source],
                ['Remote listener ready', summary?.remote_listener_ready],
                ['Signature verification required', summary?.jwt_signature_verification_required],
                ['Issuer ready', summary?.jwt_issuer_ready],
                ['Audience ready', summary?.jwt_audience_ready],
                ['Startup policy reads', summary?.startup_config_get_count],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-md border border-default bg-surface p-3 dark:border-gray-700 dark:bg-gray-900">
                  <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">{label}</div>
                  <div className="mt-1 break-all text-sm font-medium text-primary dark:text-gray-100">{display(value)}</div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Canonical runtime evidence</h4>
            <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
              <div><dt className="text-secondary">Public origin</dt><dd className="break-all font-mono text-xs">{display(summary?.public_origin)}</dd></div>
              <div><dt className="text-secondary">Configuration fingerprint</dt><dd className="break-all font-mono text-xs">{display(summary?.auth_config_fingerprint)}</dd></div>
              <div><dt className="text-secondary">Policy cache entries</dt><dd>{display(summary?.effective_policy_cache_entries)}</dd></div>
              <div><dt className="text-secondary">Support cache entries</dt><dd>{display(summary?.capability_support_cache_entries)}</dd></div>
              <div><dt className="text-secondary">Upstream calls</dt><dd>{display((summary?.upstream_effective_policy_calls || 0) + (summary?.upstream_capability_support_calls || 0))}</dd></div>
              <div><dt className="text-secondary">Upstream in flight / limit</dt><dd>{display(summary?.upstream_in_flight)} / {display(summary?.max_upstream_in_flight)}</dd></div>
              <div><dt className="text-secondary">Fail-closed rejects</dt><dd>{display(summary?.upstream_rejected)}</dd></div>
            </dl>
          </Card>

          <Card>
            <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Policy ownership</h4>
            <div className="mt-3 space-y-2 text-sm text-secondary dark:text-gray-400" data-testid="mobile-workbench-gateway-policy-owner-note">
              <p>
                Global verified administrators are managed only from{' '}
                <a className="font-medium text-blue-700 underline dark:text-blue-300" href="/settings?tab=remote_workbench_access">
                  Remote Workbench Access
                </a>
                .
              </p>
              <p>Workspace capability ingress remains managed from that workspace&apos;s Pack → Remote access page.</p>
            </div>
          </Card>

          {!strictReady ? (
            <InlineAlert
              type="warning"
              title="Gateway is not strict-policy ready"
              description={healthErrors.length > 0 ? healthErrors.join('; ') : health.reason || 'Runtime policy readiness is incomplete.'}
            />
          ) : null}
        </div>
      ) : null}
    </Section>
  );
}
