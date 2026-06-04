'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { ServerCog } from 'lucide-react';
import { settingsApi } from '../../../utils/settingsApi';
import { Card } from '../../Card';

interface RuntimeEnvironment {
  id: string;
  name?: string;
  status?: string;
  metadata?: Record<string, unknown>;
}

interface HostResourceSlot {
  runtimeId: string;
  name?: string;
  status?: string;
  adapterId?: string;
  transport?: string;
  endpoint?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function slotFromRuntime(runtime: RuntimeEnvironment): HostResourceSlot | null {
  const metadata = asRecord(runtime.metadata);
  const nested = asRecord(metadata.host_resource_slot);
  const source = Object.keys(nested).length ? nested : metadata;
  const adapterId = String(source.adapter_id || source.runtime_adapter_id || '').trim();
  if (!adapterId) return null;
  const endpoint = asRecord(source.endpoint);
  const endpointLabel = String(endpoint.base_url || source.base_url || endpoint.host || source.host || '').trim();
  return {
    runtimeId: runtime.id,
    name: runtime.name,
    status: runtime.status,
    adapterId,
    transport: String(source.transport || endpoint.transport || '').trim(),
    endpoint: endpointLabel,
  };
}

export function HostResourceSlotRegistryPanel() {
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    settingsApi
      .get<{ runtimes?: RuntimeEnvironment[] }>('/api/v1/runtime-environments')
      .then((payload) => {
        if (mounted) setRuntimes(Array.isArray(payload.runtimes) ? payload.runtimes : []);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load runtime slots');
      });
    return () => {
      mounted = false;
    };
  }, []);

  const slots = useMemo(
    () => runtimes.map(slotFromRuntime).filter((slot): slot is HostResourceSlot => Boolean(slot)),
    [runtimes],
  );

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <ServerCog className="h-4 w-4 shrink-0 text-secondary dark:text-gray-400" aria-hidden="true" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-primary dark:text-gray-100">Host Resource Slots</div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {slots.length} registered
            </div>
          </div>
        </div>
        <a
          href="/settings?tab=runtime&section=runtime-environments"
          className="inline-flex h-8 items-center rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
        >
          Register
        </a>
      </div>
      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}
      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {slots.map((slot) => (
          <div key={slot.runtimeId} className="rounded-md border border-default p-3 dark:border-gray-700">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-primary dark:text-gray-100">
                  {slot.name || slot.runtimeId}
                </div>
                <div className="mt-1 truncate text-xs text-secondary dark:text-gray-400">
                  {slot.adapterId} · {slot.transport || 'default transport'}
                </div>
              </div>
              <span className="shrink-0 rounded-md border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                {slot.status || 'unknown'}
              </span>
            </div>
            <div className="mt-2 truncate text-xs text-secondary dark:text-gray-400">
              {slot.endpoint || slot.runtimeId}
            </div>
          </div>
        ))}
        {!slots.length && !error ? (
          <div className="rounded-md border border-default p-3 text-sm text-secondary dark:border-gray-700 dark:text-gray-400">
            No host slots registered.
          </div>
        ) : null}
      </div>
    </Card>
  );
}
