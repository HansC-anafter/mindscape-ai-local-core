'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { settingsApi } from '../../utils/settingsApi';
import { Card } from '../Card';
import { Section } from '../Section';
import {
  HostResourceLaneManagerPanel,
  type HostResourceLaneManagerLane,
} from './host-resources/HostResourceLaneManagerPanel';
import { HostResourceAdapterCatalogPanel } from './host-resources/HostResourceAdapterCatalogPanel';
import { HostResourceSlotRegistryPanel } from './host-resources/HostResourceSlotRegistryPanel';
import { HostResourcesObservabilityPanel } from './host-resources/HostResourcesObservabilityPanel';
import { HostResourceWorkspaceAllocationsPanel } from './host-resources/HostResourceWorkspaceAllocationsPanel';

interface HostResourcesPanelProps {
  activeSection?: string;
  workspaceId?: string;
}

interface HostResourceLane extends HostResourceLaneManagerLane {
  lane_id: string;
}

export function HostResourcesPanel({ activeSection, workspaceId }: HostResourcesPanelProps = {}) {
  const [lanesPayload, setLanesPayload] = useState<{ lanes?: HostResourceLane[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lanes = useMemo(
    () => Array.isArray(lanesPayload?.lanes) ? lanesPayload.lanes : [],
    [lanesPayload],
  );

  const loadRegistryState = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await settingsApi.get<{ lanes?: HostResourceLane[] }>('/api/v1/host-resources/lanes');
      setLanesPayload(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load host resource lanes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeSection === 'host-resources-observability') return;
    void loadRegistryState();
  }, [activeSection, loadRegistryState]);

  if (activeSection === 'host-resources-observability') {
    return <HostResourcesObservabilityPanel />;
  }

  if (activeSection === 'workspace-resource-allocations') {
    return (
      <Section title="Workspace Allocations">
        <HostResourceWorkspaceAllocationsPanel
          lanes={lanes}
          workspaceId={workspaceId}
        />
      </Section>
    );
  }

  return (
    <Section
      title="Host Resources"
      headerRight={(
        <button
          type="button"
          onClick={() => loadRegistryState()}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      )}
    >
      <div className="space-y-4" data-testid="host-resources-registry-panel">
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        ) : null}
        <HostResourceSlotRegistryPanel />
        <HostResourceAdapterCatalogPanel />
        <HostResourceLaneManagerPanel
          lanes={lanes}
          onRefresh={loadRegistryState}
        />
        <Card className="p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-semibold text-primary dark:text-gray-100">Workspace Allocations</div>
              <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                Allocate global lanes to a workspace quota.
              </div>
            </div>
            <a
              href="/settings?tab=runtime&section=workspace-resource-allocations"
              className="inline-flex h-9 items-center rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
            >
              Open
            </a>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-semibold text-primary dark:text-gray-100">Observability</div>
              <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                {loading ? 'Loading' : `${lanes.length} lane${lanes.length === 1 ? '' : 's'}`}
              </div>
            </div>
            <a
              href="/settings?tab=runtime&section=host-resources-observability"
              className="inline-flex h-9 items-center rounded-md border border-default px-3 text-sm font-medium text-primary hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
            >
              Open
            </a>
          </div>
        </Card>
      </div>
    </Section>
  );
}
