'use client';

import React, { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import {
  LocalCoreSlotsCard,
  PackCoverageCard,
  RegistryHeaderCard,
  RoutingPolicyCard,
  RuntimeCoverageCard,
  resolveSettingsHref,
} from './ModelRouteRegistryPanelSections';
import type { PackGroup } from './ModelRouteRegistryPanelTypes';
import { useModelRouteRegistryPanelData } from './useModelRouteRegistryPanelData';

export function ModelRouteRegistryPanel() {
  const router = useRouter();
  const {
    payload,
    loading,
    error,
    reconciling,
    reconcileResult,
    reconcile,
  } = useModelRouteRegistryPanelData();

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
      <RegistryHeaderCard
        summary={payload.summary}
        driftCount={driftCount}
        reconciling={reconciling}
        reconcileResult={reconcileResult}
        onReconcile={reconcile}
      />

      {payload.policy && (
        <RoutingPolicyCard
          policy={payload.policy}
          title="Routing Policy"
          fallbackPrefix="fallback"
          fallbackLabel="Fallback"
        />
      )}

      {payload.executor_policy && (
        <RoutingPolicyCard
          policy={payload.executor_policy}
          title="Executor Runtime Policy"
          fallbackPrefix="runtime substitution"
          fallbackLabel="Runtime substitution"
        />
      )}

      <LocalCoreSlotsCard
        slots={payload.local_core_slots}
        onOpenSettings={handleOpenSettings}
      />

      <PackCoverageCard
        coverage={payload.pack_coverage}
        packGroupsById={packGroupsById}
        scannedCount={payload.summary.installed_pack_count_scanned}
        onOpenSettings={handleOpenSettings}
      />

      <RuntimeCoverageCard
        runtimes={payload.registered_runtimes}
        registeredRuntimeSlotCount={payload.summary.registered_runtime_slot_count}
        onOpenSettings={handleOpenSettings}
      />
    </div>
  );
}
