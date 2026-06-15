'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw.js';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check.js';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { Section } from '../Section';
import { StatusPill } from '../StatusPill';

interface GatewayConfigSummary {
  enabled: boolean;
  reason?: string;
  errors?: string[];
  allowed_prefix_rules?: string[];
  allowed_regex_rules?: string[];
  extra_allowed_rules?: string[];
  extra_allowed_rules_count?: number;
  allowlist_emails?: string[];
  allowlist_groups?: string[];
  workspace_allowlist?: string[];
  public_origin?: string | null;
  jwt_audience?: string[];
  jwt_issuer?: string[];
  jwt_clock_skew_seconds?: number;
  jwt_signature_verification_required?: boolean;
  jwt_verify_enabled?: boolean;
  jwt_public_key_configured?: boolean;
  gateway_policy_enabled?: boolean;
}

interface MobileWorkbenchGatewayHealth {
  status?: string;
  service?: string;
  enabled?: boolean;
  reason?: string;
  errors?: string[];
  gateway?: GatewayConfigSummary;
}

function formatList(values: string[] = [], fallback = '-') {
  if (!values.length) {
    return fallback;
  }
  return values.join(', ');
}

function countLabel(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function MobileWorkbenchGatewayPanel() {
  const [health, setHealth] = useState<MobileWorkbenchGatewayHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    setError(null);
    try {
      const data = await settingsApi.get<MobileWorkbenchGatewayHealth>(
        '/api/v1/host/services/mobile-workbench-gateway/health',
        { silent: true },
      );
      setHealth(data);
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : 'Failed to load remote workbench gateway status');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  const status = useMemo(() => {
    if (!health) {
      return { status: 'unavailable' as const, label: 'Unavailable' };
    }
    if (health.status === 'disabled' || health.enabled === false) {
      return { status: 'disabled' as const, label: 'Disabled' };
    }
    if (health.status === 'ok' || health.enabled) {
      return { status: 'enabled' as const, label: 'Enabled' };
    }
    return { status: 'unavailable' as const, label: health.status || 'Unavailable' };
  }, [health]);

  const summary = health?.gateway;
  const healthErrors = health?.errors || [];
  const healthUnreachable = health?.status === 'unreachable';
  const operatorGuardrailsConfigured = summary?.gateway_policy_enabled ?? false;
  const operatorGuardrailCount =
    (summary?.allowlist_emails || []).length
    + (summary?.allowlist_groups || []).length
    + (summary?.workspace_allowlist || []).length;
  const pathRules = [
    ...(summary?.allowed_prefix_rules || []),
    ...(summary?.allowed_regex_rules || []),
    ...(summary?.extra_allowed_rules || []),
  ];
  const showWarning = healthUnreachable || healthErrors.length > 0 || !operatorGuardrailsConfigured;

  return (
    <Section
      title={t('developerIntegrations' as any) || 'Developer Integrations'}
      description={t('developerIntegrationsDescription' as any) || 'Advanced integrations for external environments.'}
      headerRight={(
        <button
          type="button"
          onClick={() => {
            setRefreshing(true);
            void loadHealth();
          }}
          className="inline-flex items-center gap-2 rounded-md border border-default dark:border-gray-600 px-3 py-2 text-sm font-medium text-secondary dark:text-gray-300 hover:bg-surface-accent dark:hover:bg-gray-800 hover:text-primary dark:hover:text-gray-100"
          aria-label="Refresh remote workbench gateway status"
          title="Refresh remote workbench gateway status"
        >
          <RefreshCw className={refreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          <span>{t('refresh' as any) || 'Refresh'}</span>
        </button>
      )}
    >
      {loading && (
        <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4 text-sm text-secondary dark:text-gray-400">
          {t('loading' as any) || 'Loading...'}
        </div>
      )}

      {error && (
        <InlineAlert
          type="error"
          title="Remote Workbench Gateway"
          description={error}
        />
      )}

      {!loading && health && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-primary dark:text-gray-100">
                    Remote Workbench Gateway
                  </h3>
                  <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                </div>
                <p className="mt-1 text-sm text-secondary dark:text-gray-400">
                  {health.service || 'mobile-workbench-gateway'} health surface and policy summary.
                </p>
              </div>
              <StatusPill status={status.status} label={status.label} icon="" />
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-md border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 p-3">
                <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Health</div>
                <div className="mt-1 text-sm font-medium text-primary dark:text-gray-100">{health.status || 'unknown'}</div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">{health.reason || '-'}</div>
              </div>
              <div className="rounded-md border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 p-3">
                <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Operator guardrails</div>
                <div className="mt-1 text-sm font-medium text-primary dark:text-gray-100">
                  {operatorGuardrailsConfigured ? 'Configured' : 'Not configured'}
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  {countLabel(operatorGuardrailCount, 'guardrail')}
                </div>
              </div>
              <div className="rounded-md border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 p-3">
                <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Public origin</div>
                <div className="mt-1 break-all text-sm font-medium text-primary dark:text-gray-100">
                  {summary?.public_origin || '-'}
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  Canonical browser hostname for remote workbench access.
                </div>
              </div>
              <div className="rounded-md border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 p-3">
                <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Signature</div>
                <div className="mt-1 text-sm font-medium text-primary dark:text-gray-100">
                  {summary?.jwt_signature_verification_required ? 'Required' : 'Optional'}
                </div>
                <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                  {summary?.jwt_verify_enabled ? 'Public key configured' : 'Public key not configured'}
                </div>
              </div>
            </div>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Path rules</h4>
              <div className="mt-3 text-sm text-secondary dark:text-gray-400">
                {pathRules.length > 0 ? (
                  <ul className="space-y-2">
                    {pathRules.slice(0, 8).map((rule) => (
                      <li key={rule} className="rounded-md border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 px-3 py-2 font-mono text-xs text-primary dark:text-gray-200">
                        {rule}
                      </li>
                    ))}
                  </ul>
                ) : (
                  'No explicit rules configured.'
                )}
                {pathRules.length > 8 && (
                  <div className="mt-2 text-xs text-secondary dark:text-gray-400">
                    +{pathRules.length - 8} more rule(s)
                  </div>
                )}
              </div>
            </Card>

            <Card>
              <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Identity / JWT</h4>
              <div className="mt-3 space-y-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Audience</div>
                  <div className="mt-1 text-primary dark:text-gray-100 font-mono text-xs break-all">
                    {formatList(summary?.jwt_audience)}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Issuer</div>
                  <div className="mt-1 text-primary dark:text-gray-100 font-mono text-xs break-all">
                    {formatList(summary?.jwt_issuer)}
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Emails</div>
                    <div className="mt-1 text-primary dark:text-gray-100">{countLabel((summary?.allowlist_emails || []).length, 'email')}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Groups</div>
                    <div className="mt-1 text-primary dark:text-gray-100">{countLabel((summary?.allowlist_groups || []).length, 'group')}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Workspace brakes</div>
                    <div className="mt-1 text-primary dark:text-gray-100">{countLabel((summary?.workspace_allowlist || []).length, 'workspace')}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">Clock skew</div>
                    <div className="mt-1 text-primary dark:text-gray-100">{summary?.jwt_clock_skew_seconds ?? 0}s</div>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <Card>
            <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Workspace capability access</h4>
            <div className="mt-3 space-y-2 text-sm text-secondary dark:text-gray-400" data-testid="mobile-workbench-gateway-workspace-access-note">
              <p>
                Pack capability ingress is managed per workspace from the Pack panel through
                {' '}
                <span className="font-medium text-primary dark:text-gray-100">Gateway policy</span>
                .
              </p>
              <p>
                This settings panel only reports service health, public origin, identity constraints, and operator workspace brakes.
              </p>
            </div>
          </Card>

          <Card>
            <h4 className="text-sm font-semibold text-primary dark:text-gray-100">Configuration hint</h4>
            <pre className="mt-3 overflow-x-auto rounded-md border border-default dark:border-gray-700 bg-gray-950 px-3 py-3 text-xs leading-6 text-gray-100">
{`MOBILE_WORKBENCH_GATEWAY_ENABLED=1
MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN=https://remote-workbench.mindscapeai.app
MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE=remote-workbench
MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER=https://identity.example.com
MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION=1`}
            </pre>
          </Card>

          {showWarning && (
            <InlineAlert
              type="warning"
              title="Gateway policy"
              description={
                healthUnreachable
                  ? 'Health surface is unreachable.'
                  : healthErrors.length > 0
                  ? healthErrors.join('; ')
                  : 'No local operator guardrails are configured. Capability ingress still depends on each workspace gateway policy.'
              }
            />
          )}
        </div>
      )}
    </Section>
  );
}
