'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Boxes } from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';

interface RuntimeAdapter {
  adapter_id: string;
  label?: string;
  category?: string;
  worker_capable?: boolean;
  model_binding_policy?: string;
  default_model_binding_scope?: string | null;
  default_model_binding_profile?: string | null;
  transports?: string[];
}

export function HostResourceAdapterCatalogPanel() {
  const [adapters, setAdapters] = useState<RuntimeAdapter[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    settingsApi
      .get<{ adapters?: RuntimeAdapter[] }>('/api/v1/host-resources/adapter-catalog')
      .then((payload) => {
        if (mounted) setAdapters(Array.isArray(payload.adapters) ? payload.adapters : []);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load adapter catalog');
      });
    return () => {
      mounted = false;
    };
  }, []);

  const workerAdapters = useMemo(
    () => adapters.filter((adapter) => adapter.worker_capable),
    [adapters],
  );

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Boxes className="h-4 w-4 shrink-0 text-secondary dark:text-gray-400" aria-hidden="true" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-primary dark:text-gray-100">Runtime Adapter Catalog</div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {workerAdapters.length}/{adapters.length} worker capable
            </div>
          </div>
        </div>
      </div>
      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}
      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {adapters.map((adapter) => (
          <div key={adapter.adapter_id} className="rounded-md border border-default p-3 dark:border-gray-700">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-primary dark:text-gray-100">
                  {adapter.label || adapter.adapter_id}
                </div>
                <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                  {adapter.category || 'adapter'} · {adapter.model_binding_policy || 'model policy'}
                </div>
              </div>
              <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                adapter.worker_capable
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300'
              }`}>
                {adapter.worker_capable ? 'worker' : 'connector'}
              </span>
            </div>
            <div className="mt-2 truncate text-xs text-secondary dark:text-gray-400">
              {(adapter.transports || []).join(', ') || 'no transport'}
            </div>
            {adapter.default_model_binding_scope && adapter.default_model_binding_profile ? (
              <div className="mt-2 truncate text-xs text-secondary dark:text-gray-400">
                {adapter.default_model_binding_scope}.{adapter.default_model_binding_profile}
              </div>
            ) : null}
          </div>
        ))}
        {!adapters.length && !error ? (
          <div className="rounded-md border border-default p-3 text-sm text-secondary dark:border-gray-700 dark:text-gray-400">
            No adapters reported.
          </div>
        ) : null}
      </div>
    </Card>
  );
}
