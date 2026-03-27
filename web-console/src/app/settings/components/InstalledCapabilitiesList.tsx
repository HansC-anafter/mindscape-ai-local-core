'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import type { CapabilityPack } from '../types';

interface InstalledCapabilitiesListProps {
  packs?: CapabilityPack[];
  loading?: boolean;
  refreshTrigger?: number;
}

function humanizeState(value?: string | null): string {
  if (!value) {
    return 'unknown';
  }
  return value.replace(/_/g, ' ');
}

function statusClasses(state?: string | null): string {
  switch (state) {
    case 'succeeded':
    case 'installed':
    case 'active':
    case 'indexed':
      return 'bg-green-100 text-green-800 border-green-200';
    case 'pending':
    case 'running':
    case 'validation_pending':
    case 'pending_activation':
    case 'pending_restart':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'failed':
    case 'validation_failed':
    case 'activation_failed':
      return 'bg-red-100 text-red-800 border-red-200';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200';
  }
}

function formatTimestamp(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toLocaleString('zh-TW');
}

export function InstalledCapabilitiesList({ packs = [], loading = false }: InstalledCapabilitiesListProps = {}) {
  const installed = packs.filter((pack) => pack.installed);

  if (loading) {
    return <div className="text-gray-600">{t('loading' as any)}</div>;
  }

  if (installed.length === 0) {
    return (
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <p className="text-sm text-gray-600">{t('noCapabilityPacksInstalled' as any)}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900">{t('installedCapabilityPacks' as any)}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {installed.map((pack) => {
          const validationSummary = pack.validation?.summary;
          const updatedAt = formatTimestamp(
            pack.validation?.updated_at ||
            pack.activation?.updated_at ||
            pack.installed_at
          );
          const lastError = pack.activation?.last_error || pack.validation?.errors?.[0];

          return (
            <Card key={pack.id} className="flex flex-col h-full gap-4">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-gray-900 mb-1">{pack.name || pack.id}</h4>
                  <p className="text-xs text-gray-500">
                    {pack.id} v{pack.version}
                  </p>
                </div>
                {pack.activation?.activation_state === 'pending_restart' && (
                  <span className="px-2 py-1 text-xs bg-amber-100 text-amber-800 rounded whitespace-nowrap">
                    pending restart
                  </span>
                )}
              </div>

              {pack.description && (
                <p className="text-sm text-gray-600">{pack.description}</p>
              )}

              <div className="flex flex-wrap gap-2">
                <span className={`px-2 py-1 text-xs border rounded ${statusClasses(pack.activation?.install_state)}`}>
                  install: {humanizeState(pack.activation?.install_state || 'installed')}
                </span>
                <span className={`px-2 py-1 text-xs border rounded ${statusClasses(pack.activation?.activation_state)}`}>
                  activation: {humanizeState(pack.activation?.activation_state)}
                </span>
                <span className={`px-2 py-1 text-xs border rounded ${statusClasses(pack.validation?.state)}`}>
                  validation: {humanizeState(pack.validation?.state || 'not_started')}
                </span>
              </div>

              {validationSummary && (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    validated {validationSummary.validated}
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    failed {validationSummary.failed}
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    skipped {validationSummary.skipped}
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    warnings {validationSummary.warnings}
                  </div>
                </div>
              )}

              <div className="space-y-1 text-xs text-gray-500">
                {pack.validation?.mode && (
                  <div>validation mode: {pack.validation.mode}</div>
                )}
                {updatedAt && (
                  <div>updated: {updatedAt}</div>
                )}
              </div>

              {lastError && (
                <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {lastError}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
