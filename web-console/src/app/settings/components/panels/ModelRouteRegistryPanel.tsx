'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { getApiBaseUrl } from '../../../../lib/api-url';
import { Card } from '../Card';

interface ModelRouteSlot {
  slot_id: string;
  slot_kind: string;
  title: string;
  summary: string;
  source: string;
  settings_anchor?: string | null;
  evidence_path?: string | null;
}

interface PackCoverageEntry {
  pack_id: string;
  name: string;
  installed: boolean;
  enabled: boolean;
  slot_count: number;
  live_slot_count: number;
  stored_slot_count: number;
  registration_drift: boolean;
  slot_kinds: string[];
}

interface PackGroup {
  pack_id: string;
  name: string;
  slot_count: number;
  registration_drift: boolean;
  slot_kinds: string[];
  slots: ModelRouteSlot[];
}

interface RuntimeGroup {
  runtime_id: string;
  name: string;
  status: string;
  slot_count: number;
  stored_slot_count?: number;
  registration_drift?: boolean;
  slots: ModelRouteSlot[];
}

interface ModelRouteRegistryPayload {
  summary: {
    total_slot_count: number;
    local_core_slot_count: number;
    installed_pack_count_scanned: number;
    installed_pack_count_with_slots: number;
    installed_pack_slot_count: number;
    registered_runtime_count: number;
    registered_runtime_slot_count: number;
    packs_with_registration_drift: string[];
  };
  local_core_slots: ModelRouteSlot[];
  pack_groups: PackGroup[];
  pack_coverage: PackCoverageEntry[];
  registered_runtimes: RuntimeGroup[];
}

interface ReconcileResult {
  updated_pack_count: number;
  updated_runtime_count: number;
}

function MetricCard({ label, value, tone = 'neutral' }: { label: string; value: number; tone?: 'neutral' | 'danger' }) {
  const toneClass = tone === 'danger'
    ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200'
    : 'border-default bg-surface-secondary text-primary dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100';

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`}>
      <div className="text-xs font-medium uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function SlotChip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'danger' | 'success' }) {
  const toneClass = tone === 'danger'
    ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-200'
    : tone === 'success'
      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200'
      : 'bg-surface-accent text-secondary dark:bg-gray-700 dark:text-gray-200';

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${toneClass}`}>
      {children}
    </span>
  );
}

function resolveSettingsHref(anchor?: string | null): string | null {
  const text = String(anchor || '').trim();
  if (!text) {
    return null;
  }
  if (text.startsWith('basic:')) {
    return `/settings?tab=basic&section=${encodeURIComponent(text.slice('basic:'.length))}`;
  }
  if (text.startsWith('credentials:')) {
    return `/settings?tab=credentials&section=${encodeURIComponent(text.slice('credentials:'.length))}`;
  }
  if (text.startsWith('settings:')) {
    const section = text.slice('settings:'.length);
    if (section === 'runtime-environments' || section === 'workflow-engines') {
      return '/settings?tab=runtime';
    }
    return `/settings?tab=basic&section=${encodeURIComponent(section)}`;
  }
  if (text === 'tab:runtime') {
    return '/settings?tab=runtime';
  }
  return null;
}

export function ModelRouteRegistryPanel() {
  const router = useRouter();
  const isMountedRef = useRef(true);
  const [payload, setPayload] = useState<ModelRouteRegistryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResult | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const apiUrl = getApiBaseUrl();
      const response = await fetch(`${apiUrl}/api/v1/settings/model-route-registry`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (isMountedRef.current) {
        setPayload(data);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load model route registry');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    void load();
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const packGroupsById = useMemo(() => {
    const map = new Map<string, PackGroup>();
    (payload?.pack_groups || []).forEach((group) => map.set(group.pack_id, group));
    return map;
  }, [payload]);

  const handleOpenSettings = (anchor?: string | null) => {
    const href = resolveSettingsHref(anchor);
    if (href) {
      router.push(href);
    }
  };

  const handleReconcile = async () => {
    try {
      setReconciling(true);
      setReconcileResult(null);
      const apiUrl = getApiBaseUrl();
      const response = await fetch(`${apiUrl}/api/v1/settings/model-route-registry/reconcile`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setReconcileResult({
        updated_pack_count: Number(data.updated_pack_count || 0),
        updated_runtime_count: Number(data.updated_runtime_count || 0),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reconcile model route registry');
    } finally {
      setReconciling(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="py-8 text-sm text-secondary dark:text-gray-400">
          {t('loading' as any) || 'Loading...'}
        </div>
      </Card>
    );
  }

  if (error || !payload) {
    return (
      <Card>
        <div className="py-8 text-sm text-rose-600 dark:text-rose-300">
          {error || 'Failed to load model route registry'}
        </div>
      </Card>
    );
  }

  const driftCount = payload.summary.packs_with_registration_drift.length;

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
              {t('modelRoutingRegistry' as any)}
            </h2>
            <p className="mt-1 text-sm text-secondary dark:text-gray-400">
              {t('modelRoutingRegistryDescription' as any)}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleReconcile}
              disabled={reconciling}
              className="rounded-lg border border-default px-3 py-2 text-sm font-medium text-primary transition hover:bg-surface-secondary disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
            >
              {reconciling ? (t('loading' as any) || 'Loading...') : t('reconcileModelRouteRegistry' as any)}
            </button>
            {reconcileResult && (
              <div className="text-sm text-secondary dark:text-gray-400">
                {t('modelRouteRegistryReconciled' as any)} {reconcileResult.updated_pack_count} · {t('modelRouteRegistryRuntimeReconciled' as any)} {reconcileResult.updated_runtime_count}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label={t('modelRoutingTotalSlots' as any)}
              value={payload.summary.total_slot_count}
            />
            <MetricCard
              label={t('modelRoutingInstalledPacks' as any)}
              value={payload.summary.installed_pack_count_with_slots}
            />
            <MetricCard
              label={t('modelRoutingRegisteredRuntimes' as any)}
              value={payload.summary.registered_runtime_count}
            />
            <MetricCard
              label={t('modelRoutingRegistrationDrift' as any)}
              value={driftCount}
              tone={driftCount > 0 ? 'danger' : 'neutral'}
            />
          </div>
        </div>
      </Card>

      <Card>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-primary dark:text-gray-100">
              {t('modelRoutingLocalCore' as any)}
            </h3>
            <SlotChip>{payload.local_core_slots.length} {t('routeSlots' as any)}</SlotChip>
          </div>
          <div className="space-y-3">
            {payload.local_core_slots.map((slot) => (
              <div key={slot.slot_id} className="rounded-xl border border-default p-4 dark:border-gray-700">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-primary dark:text-gray-100">{slot.title}</div>
                    <SlotChip>{slot.slot_kind}</SlotChip>
                  </div>
                  {resolveSettingsHref(slot.settings_anchor) && (
                    <button
                      type="button"
                      onClick={() => handleOpenSettings(slot.settings_anchor)}
                      className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
                    >
                      {t('openSlotSettings' as any)}
                    </button>
                  )}
                </div>
                <div className="mt-2 text-sm text-secondary dark:text-gray-400">{slot.summary}</div>
                <div className="mt-2 text-xs text-tertiary dark:text-gray-500">{slot.source}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <Card>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-primary dark:text-gray-100">
              {t('modelRoutingPackCoverage' as any)}
            </h3>
            <SlotChip>{payload.summary.installed_pack_count_scanned} {t('installed' as any)}</SlotChip>
          </div>
          <div className="space-y-4">
            {payload.pack_coverage.map((entry) => {
              const group = packGroupsById.get(entry.pack_id);
              return (
                <div key={entry.pack_id} className="rounded-xl border border-default p-4 dark:border-gray-700">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-primary dark:text-gray-100">{entry.name}</div>
                      <SlotChip tone={entry.enabled ? 'success' : 'neutral'}>
                        {entry.enabled ? t('enabled' as any) : t('disabled' as any)}
                      </SlotChip>
                      <SlotChip>{entry.slot_count} {t('routeSlots' as any)}</SlotChip>
                      {entry.registration_drift && (
                        <SlotChip tone="danger">{t('registrationDrift' as any)}</SlotChip>
                      )}
                    </div>
                    {group?.slots.some((slot) => resolveSettingsHref(slot.settings_anchor)) && (
                      <button
                        type="button"
                        onClick={() => handleOpenSettings(group.slots.find((slot) => resolveSettingsHref(slot.settings_anchor))?.settings_anchor)}
                        className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
                      >
                        {t('openSlotSettings' as any)}
                      </button>
                    )}
                  </div>
                  <div className="mt-2 text-xs text-secondary dark:text-gray-400">
                    live={entry.live_slot_count} · stored={entry.stored_slot_count}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {entry.slot_kinds.map((kind) => (
                      <SlotChip key={`${entry.pack_id}-${kind}`}>{kind}</SlotChip>
                    ))}
                  </div>
                  {group && group.slots.length > 0 ? (
                    <div className="mt-4 grid gap-3">
                      {group.slots.map((slot) => (
                        <div key={slot.slot_id} className="rounded-lg bg-surface-secondary px-3 py-3 dark:bg-gray-800">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-primary dark:text-gray-100">{slot.title}</div>
                            {resolveSettingsHref(slot.settings_anchor) && (
                              <button
                                type="button"
                                onClick={() => handleOpenSettings(slot.settings_anchor)}
                                className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
                              >
                                {t('openSlotSettings' as any)}
                              </button>
                            )}
                          </div>
                          <div className="mt-1 text-sm text-secondary dark:text-gray-400">{slot.summary}</div>
                          <div className="mt-2 text-xs text-tertiary dark:text-gray-500">{slot.source}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 text-sm text-secondary dark:text-gray-400">
                      {t('noModelRouteSlots' as any)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <Card>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-primary dark:text-gray-100">
              {t('modelRoutingRuntimeCoverage' as any)}
            </h3>
            <SlotChip>{payload.summary.registered_runtime_slot_count} {t('routeSlots' as any)}</SlotChip>
          </div>
          <div className="space-y-3">
            {payload.registered_runtimes.map((runtime) => (
              <div key={runtime.runtime_id} className="rounded-xl border border-default p-4 dark:border-gray-700">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-primary dark:text-gray-100">{runtime.name}</div>
                    <SlotChip>{runtime.status}</SlotChip>
                    {runtime.registration_drift && (
                      <SlotChip tone="danger">{t('registrationDrift' as any)}</SlotChip>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleOpenSettings('tab:runtime')}
                    className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
                  >
                    {t('openSlotSettings' as any)}
                  </button>
                </div>
                {typeof runtime.stored_slot_count === 'number' && (
                  <div className="mt-2 text-xs text-secondary dark:text-gray-400">
                    live={runtime.slot_count} · stored={runtime.stored_slot_count}
                  </div>
                )}
                <div className="mt-3 space-y-3">
                  {runtime.slots.map((slot) => (
                    <div key={slot.slot_id} className="rounded-lg bg-surface-secondary px-3 py-3 dark:bg-gray-800">
                      <div className="text-sm font-medium text-primary dark:text-gray-100">{slot.title}</div>
                      <div className="mt-1 text-sm text-secondary dark:text-gray-400">{slot.summary}</div>
                      <div className="mt-2 text-xs text-tertiary dark:text-gray-500">{slot.source}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
