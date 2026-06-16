import React from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import type {
  ModelRouteRegistryPayload,
  ModelRouteSlot,
  PackCoverageEntry,
  PackGroup,
  ReconcileResult,
  RoutingPolicyPayload,
  RuntimeGroup,
} from './ModelRouteRegistryPanelTypes';

type OpenSettingsHandler = (anchor?: string | null) => void;

export function MetricCard({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: number;
  tone?: 'neutral' | 'danger';
}) {
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

export function SlotChip({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'danger' | 'success';
}) {
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

export function resolveSettingsHref(anchor?: string | null): string | null {
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

export function RegistryHeaderCard({
  summary,
  driftCount,
  reconciling,
  reconcileResult,
  onReconcile,
}: {
  summary: ModelRouteRegistryPayload['summary'];
  driftCount: number;
  reconciling: boolean;
  reconcileResult: ReconcileResult | null;
  onReconcile: () => void;
}) {
  return (
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
            onClick={onReconcile}
            disabled={reconciling}
            className="rounded-lg border border-default px-3 py-2 text-sm font-medium text-primary transition hover:bg-surface-secondary disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
          >
            {reconciling ? (t('loading' as any) || 'Loading...') : t('reconcileModelRouteRegistry' as any)}
          </button>
          {reconcileResult && (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('modelRouteRegistryReconciled' as any)} {reconcileResult.updated_pack_count} - {t('modelRouteRegistryRuntimeReconciled' as any)} {reconcileResult.updated_runtime_count}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label={t('modelRoutingTotalSlots' as any)}
            value={summary.total_slot_count}
          />
          <MetricCard
            label={t('modelRoutingInstalledPacks' as any)}
            value={summary.installed_pack_count_with_slots}
          />
          <MetricCard
            label={t('modelRoutingRegisteredRuntimes' as any)}
            value={summary.registered_runtime_count}
          />
          <MetricCard
            label={t('modelRoutingRegistrationDrift' as any)}
            value={driftCount}
            tone={driftCount > 0 ? 'danger' : 'neutral'}
          />
        </div>
      </div>
    </Card>
  );
}

export function RoutingPolicyCard({
  policy,
  title,
  fallbackPrefix,
  fallbackLabel,
}: {
  policy: RoutingPolicyPayload;
  title: string;
  fallbackPrefix: string;
  fallbackLabel: string;
}) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {title}
          </h3>
          <SlotChip tone={policy.fallback_policy.allowed ? 'danger' : 'success'}>
            {fallbackPrefix} {policy.fallback_policy.allowed ? 'allowed' : 'disallowed'}
          </SlotChip>
        </div>

        <div className="rounded-xl border border-default p-4 dark:border-gray-700">
          <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">
            Authority
          </div>
          <div className="mt-1 text-sm font-medium text-primary dark:text-gray-100">
            {policy.route_authority}
          </div>
          <div className="mt-3 text-xs uppercase tracking-wide text-secondary dark:text-gray-400">
            Workspace override
          </div>
          <div className="mt-1 text-sm text-secondary dark:text-gray-300">
            {policy.workspace_override.summary}
          </div>
        </div>

        <div className="rounded-xl border border-default p-4 dark:border-gray-700">
          <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">
            Precedence
          </div>
          <div className="mt-3 space-y-3">
            {policy.precedence.map((item) => (
              <div key={item.key} className="rounded-lg bg-surface-secondary px-3 py-3 dark:bg-gray-800">
                <div className="flex items-center gap-2">
                  <div className="text-sm font-medium text-primary dark:text-gray-100">{item.label}</div>
                  <SlotChip tone={item.active ? 'success' : 'neutral'}>
                    {item.active ? 'active' : 'inactive'}
                  </SlotChip>
                </div>
                <div className="mt-1 text-sm text-secondary dark:text-gray-400">{item.summary}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-default p-4 dark:border-gray-700">
          <div className="text-xs uppercase tracking-wide text-secondary dark:text-gray-400">
            {fallbackLabel}
          </div>
          <div className="mt-1 text-sm font-medium text-primary dark:text-gray-100">
            {policy.fallback_policy.mode}
          </div>
          <div className="mt-2 text-sm text-secondary dark:text-gray-400">
            {policy.fallback_policy.summary}
          </div>
        </div>
      </div>
    </Card>
  );
}

function SlotRow({
  slot,
  onOpenSettings,
  variant = 'bordered',
}: {
  slot: ModelRouteSlot;
  onOpenSettings: OpenSettingsHandler;
  variant?: 'bordered' | 'filled' | 'runtime';
}) {
  const containerClass = variant === 'bordered'
    ? 'rounded-xl border border-default p-4 dark:border-gray-700'
    : 'rounded-lg bg-surface-secondary px-3 py-3 dark:bg-gray-800';
  const href = resolveSettingsHref(slot.settings_anchor);
  const summaryClass = variant === 'bordered'
    ? 'mt-2 text-sm text-secondary dark:text-gray-400'
    : 'mt-1 text-sm text-secondary dark:text-gray-400';

  return (
    <div className={containerClass}>
      {variant === 'runtime' ? (
        <div className="text-sm font-medium text-primary dark:text-gray-100">{slot.title}</div>
      ) : variant === 'filled' ? (
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-medium text-primary dark:text-gray-100">{slot.title}</div>
          {href && (
            <button
              type="button"
              onClick={() => onOpenSettings(slot.settings_anchor)}
              className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
            >
              {t('openSlotSettings' as any)}
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="font-medium text-primary dark:text-gray-100">{slot.title}</div>
            <SlotChip>{slot.slot_kind}</SlotChip>
          </div>
          {href && (
            <button
              type="button"
              onClick={() => onOpenSettings(slot.settings_anchor)}
              className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
            >
              {t('openSlotSettings' as any)}
            </button>
          )}
        </div>
      )}
      <div className={summaryClass}>{slot.summary}</div>
      <div className="mt-2 text-xs text-tertiary dark:text-gray-500">{slot.source}</div>
    </div>
  );
}

export function LocalCoreSlotsCard({
  slots,
  onOpenSettings,
}: {
  slots: ModelRouteSlot[];
  onOpenSettings: OpenSettingsHandler;
}) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('modelRoutingLocalCore' as any)}
          </h3>
          <SlotChip>{slots.length} {t('routeSlots' as any)}</SlotChip>
        </div>
        <div className="space-y-3">
          {slots.map((slot) => (
            <SlotRow key={slot.slot_id} slot={slot} onOpenSettings={onOpenSettings} />
          ))}
        </div>
      </div>
    </Card>
  );
}

export function PackCoverageCard({
  coverage,
  packGroupsById,
  scannedCount,
  onOpenSettings,
}: {
  coverage: PackCoverageEntry[];
  packGroupsById: Map<string, PackGroup>;
  scannedCount: number;
  onOpenSettings: OpenSettingsHandler;
}) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('modelRoutingPackCoverage' as any)}
          </h3>
          <SlotChip>{scannedCount} {t('installed' as any)}</SlotChip>
        </div>
        <div className="space-y-4">
          {coverage.map((entry) => (
            <PackCoverageEntryCard
              key={entry.pack_id}
              entry={entry}
              group={packGroupsById.get(entry.pack_id)}
              onOpenSettings={onOpenSettings}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}

function PackCoverageEntryCard({
  entry,
  group,
  onOpenSettings,
}: {
  entry: PackCoverageEntry;
  group?: PackGroup;
  onOpenSettings: OpenSettingsHandler;
}) {
  const firstSettingsAnchor = group?.slots.find((slot) => resolveSettingsHref(slot.settings_anchor))?.settings_anchor;

  return (
    <div className="rounded-xl border border-default p-4 dark:border-gray-700">
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
        {firstSettingsAnchor && (
          <button
            type="button"
            onClick={() => onOpenSettings(firstSettingsAnchor)}
            className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
          >
            {t('openSlotSettings' as any)}
          </button>
        )}
      </div>
      <div className="mt-2 text-xs text-secondary dark:text-gray-400">
        live={entry.live_slot_count} - stored={entry.stored_slot_count}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {entry.slot_kinds.map((kind) => (
          <SlotChip key={`${entry.pack_id}-${kind}`}>{kind}</SlotChip>
        ))}
      </div>
      {group && group.slots.length > 0 ? (
        <div className="mt-4 grid gap-3">
          {group.slots.map((slot) => (
            <SlotRow
              key={slot.slot_id}
              slot={slot}
              onOpenSettings={onOpenSettings}
              variant="filled"
            />
          ))}
        </div>
      ) : (
        <div className="mt-4 text-sm text-secondary dark:text-gray-400">
          {t('noModelRouteSlots' as any)}
        </div>
      )}
    </div>
  );
}

export function RuntimeCoverageCard({
  runtimes,
  registeredRuntimeSlotCount,
  onOpenSettings,
}: {
  runtimes: RuntimeGroup[];
  registeredRuntimeSlotCount: number;
  onOpenSettings: OpenSettingsHandler;
}) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('modelRoutingRuntimeCoverage' as any)}
          </h3>
          <SlotChip>{registeredRuntimeSlotCount} {t('routeSlots' as any)}</SlotChip>
        </div>
        <div className="space-y-3">
          {runtimes.map((runtime) => (
            <RuntimeGroupCard
              key={runtime.runtime_id}
              runtime={runtime}
              onOpenSettings={onOpenSettings}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}

function RuntimeGroupCard({
  runtime,
  onOpenSettings,
}: {
  runtime: RuntimeGroup;
  onOpenSettings: OpenSettingsHandler;
}) {
  return (
    <div className="rounded-xl border border-default p-4 dark:border-gray-700">
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
          onClick={() => onOpenSettings('tab:runtime')}
          className="text-xs font-medium text-secondary underline-offset-2 hover:underline dark:text-gray-300"
        >
          {t('openSlotSettings' as any)}
        </button>
      </div>
      {typeof runtime.stored_slot_count === 'number' && (
        <div className="mt-2 text-xs text-secondary dark:text-gray-400">
          live={runtime.slot_count} - stored={runtime.stored_slot_count}
        </div>
      )}
      <div className="mt-3 space-y-3">
        {runtime.slots.map((slot) => (
          <SlotRow
            key={slot.slot_id}
            slot={slot}
            onOpenSettings={onOpenSettings}
            variant="runtime"
          />
        ))}
      </div>
    </div>
  );
}
