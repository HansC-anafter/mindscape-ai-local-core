'use client';

import React, { useEffect, useState } from 'react';

import { Activity, PauseCircle } from 'lucide-react';

import WorkspacePausedRunsPanel from '@/components/workspace/WorkspacePausedRunsPanel';
import WorkspaceRunObservationsPanel from '@/components/workspace/WorkspaceRunObservationsPanel';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import type {
  CapabilityUiLocalizationBridgeV1,
} from '@/lib/capability-ui-localization';
import { useT } from '@/lib/i18n';
import {
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';
import type { UseRunObservationsSummaryResult } from '@/lib/workspace-runs/useRunObservationsSummary';
import { useCapabilityHostLocalizationPromise } from './CapabilityHostLocalizationContext';
import WorkspaceRunsFallbackPanel from './WorkspaceRunsFallbackPanel';
import { getWorkspaceToolDefinitions } from './useWorkspaceToolDefinitions';

interface WorkspaceRunsPanelProps {
  workspaceId: string;
  activeCapabilityCode: string | null;
  runObservationsSummary?: UseRunObservationsSummaryResult;
}

type WorkspaceRunsView = 'active' | 'paused';

function isRunsPanelTool(tool: WorkspaceToolDefinition): boolean {
  return tool.id === 'runs_panel' && tool.group === 'capability';
}

function WorkspaceRunsViewTabs({
  activeView,
  setActiveView,
}: {
  activeView: WorkspaceRunsView;
  setActiveView: (view: WorkspaceRunsView) => void;
}) {
  const t = useT();
  const tabs = [
    {
      id: 'active' as const,
      label: t('workspaceToolActiveRuns'),
      shortLabel: t('workspaceToolActive'),
      icon: Activity,
    },
    {
      id: 'paused' as const,
      label: t('workspaceToolPausedRuns'),
      shortLabel: t('workspaceToolPaused'),
      icon: PauseCircle,
    },
  ];
  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-gray-200 px-2 py-2 dark:border-gray-800">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const active = activeView === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            data-testid={`workspace-runs-view-${tab.id}`}
            onClick={() => setActiveView(tab.id)}
            className={`h-8 rounded-md border px-2 text-xs font-semibold uppercase tracking-normal flex items-center gap-2 ${
              active
                ? 'border-gray-300 bg-gray-100 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100'
                : 'border-transparent bg-transparent text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800/70'
            }`}
            aria-label={tab.label}
            title={tab.label}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{tab.shortLabel}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function WorkspaceRunsPanel({
  workspaceId,
  activeCapabilityCode,
  runObservationsSummary,
}: WorkspaceRunsPanelProps) {
  const apiUrl = getApiBaseUrl();
  const t = useT();
  const workspaceData = useWorkspaceDataOptional();
  const localizationPromise =
    useCapabilityHostLocalizationPromise(activeCapabilityCode);
  const [activeView, setActiveView] = useState<WorkspaceRunsView>('active');
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const [localization, setLocalization] =
    useState<CapabilityUiLocalizationBridgeV1 | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void workspaceData?.refreshExecutions?.();
  }, [workspaceData?.refreshExecutions]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setComponent(null);
    setLocalization(null);
    if (!activeCapabilityCode) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    void getWorkspaceToolDefinitions(apiUrl, activeCapabilityCode, workspaceId)
      .then(async (tools) => {
        const runsPanelTool = tools.find(isRunsPanelTool);
        if (!runsPanelTool) {
          return null;
        }
        if (!localizationPromise) {
          throw new Error('capability_host_localization_pending');
        }
        const {
          loadCapabilityUIComponent,
          primeCapabilityUIComponentMetadata,
        } = await import('@/lib/capability-ui-loader');
        primeCapabilityUIComponentMetadata(
          runsPanelTool.capability_code,
          [runsPanelTool.panel_component],
        );
        return Promise.all([
          loadCapabilityUIComponent(
            runsPanelTool.capability_code,
            runsPanelTool.panel_component_code,
            apiUrl,
            workspaceId,
          ),
          localizationPromise,
        ]);
      })
      .then((loaded) => {
        if (!cancelled) {
          setComponent(() => loaded?.[0] || null);
          setLocalization(loaded?.[1] || null);
          setLoading(false);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          if (
            loadError instanceof Error
            && loadError.message === 'capability_host_localization_pending'
          ) {
            return;
          }
          setComponent(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeCapabilityCode, apiUrl, localizationPromise, workspaceId]);

  const activeContent = loading ? (
    <div className="p-2 text-xs text-gray-500 dark:text-gray-400">
      {t('workspaceToolLoadingRuns')}
    </div>
  ) : !Component ? (
    <>
      <WorkspaceRunObservationsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} compact showEmptyState={false} />
      <WorkspaceRunsFallbackPanel workspaceId={workspaceId} apiUrl={apiUrl} />
    </>
  ) : (
    <div className="min-h-0 flex-1 overflow-hidden">
      <Component
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        embedded
        localization={localization}
      />
    </div>
  );

  if (activeView === 'paused') {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <WorkspaceRunsViewTabs activeView={activeView} setActiveView={setActiveView} />
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          <WorkspacePausedRunsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceRunsViewTabs activeView={activeView} setActiveView={setActiveView} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {activeContent}
      </div>
    </div>
  );
}
