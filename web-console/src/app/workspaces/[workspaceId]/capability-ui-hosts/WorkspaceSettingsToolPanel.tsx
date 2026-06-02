'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  ExternalLink,
  HardDrive,
  PlayCircle,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  SlidersHorizontal,
} from 'lucide-react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { isDocumentHidden } from '@/lib/page-visibility';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import {
  WorkspaceAgentsStatusCard,
  type WorkspaceAgentsStatusSnapshot,
} from '@/components/workspace/WorkspaceAgentsStatusCard';
import { WorkspaceExecutionSettingsControls } from '@/components/workspace/WorkspaceExecutionSettingsControls';
import { WorkspaceToolOverlayFloatingPanel } from '@/components/workspace/WorkspaceToolOverlayFloatingPanel';
import {
  HostResourceStatusSummaryCard,
  type HostResourceSummary,
} from './HostResourceStatusSummaryCard';

const CapabilityExtensionSlot = React.lazy(() => import('../components/CapabilityExtensionSlot'));
const StoragePathConfigModal = React.lazy(() => import('@/components/StoragePathConfigModal'));

type SettingsSection = 'Status' | 'Workspace' | 'Execution' | 'Tools' | 'Data';

interface WorkspaceSettingsToolPanelProps {
  workspaceId: string;
  apiUrl: string;
}

const SECTIONS: Array<{ id: SettingsSection; icon: React.ReactNode }> = [
  { id: 'Status', icon: <RefreshCw aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Workspace', icon: <SettingsIcon aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Execution', icon: <Bot aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Tools', icon: <SlidersHorizontal aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Data', icon: <Database aria-hidden="true" className="h-4 w-4" /> },
];

interface StatusSnapshot {
  agents: WorkspaceAgentsStatusSnapshot | null;
  xtts: Record<string, any> | null;
  mcpGateway: Record<string, any> | null;
  hostResources: HostResourceSummary | null;
  updatedAt: string;
}

function formatList(values: unknown): string {
  if (!Array.isArray(values) || values.length === 0) {
    return '';
  }
  return values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0).join(', ');
}

function parseList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function WorkspaceSettingsToolPanel({
  workspaceId,
  apiUrl,
}: WorkspaceSettingsToolPanelProps) {
  const [openSections, setOpenSections] = useState<Record<SettingsSection, boolean>>({
    Status: true,
    Workspace: false,
    Execution: false,
    Tools: false,
    Data: false,
  });

  const toggleSection = (sectionId: SettingsSection) => {
    setOpenSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }));
  };

  const renderSectionContent = (sectionId: SettingsSection) => {
    if (sectionId === 'Status') {
      return <StatusSection apiUrl={apiUrl} workspaceId={workspaceId} />;
    }
    if (sectionId === 'Workspace') {
      return <WorkspaceSection apiUrl={apiUrl} />;
    }
    if (sectionId === 'Execution') {
      return <ExecutionSection apiUrl={apiUrl} workspaceId={workspaceId} />;
    }
    if (sectionId === 'Tools') {
      return <ToolEnginesSection workspaceId={workspaceId} />;
    }
    return <DataSection apiUrl={apiUrl} workspaceId={workspaceId} />;
  };

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-100"
      data-testid="workspace-settings-panel"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2" data-testid="workspace-settings-panel-body">
        <div className="space-y-2" data-testid="workspace-settings-section-stack">
          {SECTIONS.map((section) => {
            const isOpen = openSections[section.id];
            const sectionKey = section.id.toLowerCase();
            return (
              <section
                key={section.id}
                className="overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
                data-testid={`workspace-settings-section-${sectionKey}`}
              >
                <button
                  type="button"
                  className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left ${
                    isOpen
                      ? 'bg-gray-100 text-gray-950 dark:bg-gray-900 dark:text-white'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-950 dark:text-gray-300 dark:hover:bg-gray-900 dark:hover:text-white'
                  }`}
                  aria-expanded={isOpen}
                  aria-controls={`workspace-settings-section-body-${sectionKey}`}
                  onClick={() => toggleSection(section.id)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {isOpen ? (
                      <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0" />
                    ) : (
                      <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0" />
                    )}
                    <span className="shrink-0">{section.icon}</span>
                    <span className="text-sm font-semibold">{section.id}</span>
                  </span>
                </button>
                {isOpen ? (
                  <div
                    id={`workspace-settings-section-body-${sectionKey}`}
                    className="border-t border-gray-200 p-3 dark:border-gray-800"
                    data-testid={`workspace-settings-${sectionKey}-section-panel`}
                  >
                    {renderSectionContent(section.id)}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StatusSection({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const workspaceData = useWorkspaceDataOptional();
  const [loading, setLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<StatusSnapshot | null>(null);
  const refreshAllWorkspace = workspaceData?.refreshAll;
  const refreshSystemStatus = workspaceData?.refreshSystemStatus;

  const loadSnapshot = React.useCallback(async (shouldRefreshAll: boolean) => {
    if (isDocumentHidden()) {
      return;
    }
    setLoading(true);
    setStatusError(null);
    try {
      let workspaceStatusRefresh = Promise.resolve();
      if (shouldRefreshAll) {
        workspaceStatusRefresh = refreshAllWorkspace
          ? refreshAllWorkspace()
          : (refreshSystemStatus ? refreshSystemStatus({ force: true }) : Promise.resolve());
      }
      const [agents, xtts, mcpGateway, hostResources] = await Promise.allSettled([
        fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/agents`),
        fetch(`${apiUrl}/api/v1/host/services/xtts/health`),
        fetch(`${apiUrl}/api/v1/host/services/mcp-gateway/health`),
        fetch(`${apiUrl}/api/v1/host-resources/summary${shouldRefreshAll ? '?refresh=true' : '?allow_stale=true'}`),
        workspaceStatusRefresh,
      ]);
      setSnapshot({
        agents: agents.status === 'fulfilled' && agents.value.ok ? await agents.value.json().catch(() => null) : null,
        xtts: xtts.status === 'fulfilled' && xtts.value.ok ? await xtts.value.json().catch(() => null) : null,
        mcpGateway: mcpGateway.status === 'fulfilled' && mcpGateway.value.ok ? await mcpGateway.value.json().catch(() => null) : null,
        hostResources: hostResources.status === 'fulfilled' && hostResources.value.ok
          ? await hostResources.value.json().catch(() => null)
          : null,
        updatedAt: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : 'Status refresh failed');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, refreshAllWorkspace, refreshSystemStatus, workspaceId]);

  useEffect(() => {
    void loadSnapshot(false);
  }, [loadSnapshot]);

  const systemStatus = workspaceData?.systemStatus;
  return (
    <div className="space-y-3" data-testid="workspace-settings-status-section">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">System</div>
          <div className="truncate text-sm font-semibold">{systemStatus?.llm_provider || 'Runtime snapshot'}</div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label="Refresh status"
          onClick={() => void loadSnapshot(true)}
        >
          <RefreshCw aria-hidden="true" className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatusMetric label="LLM" value={systemStatus?.llm_configured ? 'Ready' : 'Unset'} />
        <StatusMetric label="Vector DB" value={systemStatus?.vector_db_connected ? 'Ready' : 'Offline'} />
        <StatusMetric label="Issues" value={String(systemStatus?.critical_issues_count ?? 0)} />
        <StatusMetric label="Updated" value={snapshot?.updatedAt || '-'} />
      </div>
      <WorkspaceAgentsStatusCard workspaceId={workspaceId} agentsSnapshot={snapshot?.agents || null} />
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex justify-between gap-2 py-1">
          <span className="text-gray-500 dark:text-gray-400">XTTS</span>
          <span className="truncate font-medium">{snapshot?.xtts?.status || snapshot?.xtts?.state || 'Unchecked'}</span>
        </div>
        <div className="flex justify-between gap-2 py-1">
          <span className="text-gray-500 dark:text-gray-400">MCP Gateway</span>
          <span className="truncate font-medium">{snapshot?.mcpGateway?.status || snapshot?.mcpGateway?.state || 'Unchecked'}</span>
        </div>
      </div>
      <HostResourceStatusSummaryCard
        summary={snapshot?.hostResources || null}
        loading={loading}
        onOpenDashboard={() => openAppRouteInNewWindow(`/settings?tab=runtime&section=host-resources&workspace_id=${encodeURIComponent(workspaceId)}`)}
      />
      {statusError ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {statusError}
        </div>
      ) : null}
    </div>
  );
}

function StatusMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
      <div className="text-[10px] font-semibold uppercase text-gray-500 dark:text-gray-400">{label}</div>
      <div className="truncate text-sm font-semibold">{value}</div>
    </div>
  );
}

function WorkspaceSection({ apiUrl }: { apiUrl: string }) {
  const workspaceData = useWorkspaceDataOptional();
  const workspace = workspaceData?.workspace;
  const [executionMode, setExecutionMode] = useState('hybrid');
  const [executionPriority, setExecutionPriority] = useState('medium');
  const [expectedArtifacts, setExpectedArtifacts] = useState('');
  const [intentAutoExecute, setIntentAutoExecute] = useState(false);
  const [intentThreshold, setIntentThreshold] = useState(0.8);
  const [sgrEnabled, setSgrEnabled] = useState(false);
  const [sgrMode, setSgrMode] = useState<'inline' | 'two_pass'>('inline');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const meta = workspace?.metadata || {};
    const intentConfig = workspace?.playbook_auto_execution_config?.intent_extraction || {};
    setExecutionMode(workspace?.execution_mode || 'hybrid');
    setExecutionPriority(workspace?.execution_priority || 'medium');
    setExpectedArtifacts(formatList(workspace?.expected_artifacts));
    setIntentAutoExecute(Boolean(intentConfig.auto_execute));
    setIntentThreshold(Number(intentConfig.confidence_threshold || 0.8));
    setSgrEnabled(Boolean(meta.sgr_enabled));
    setSgrMode(meta.sgr_mode === 'two_pass' ? 'two_pass' : 'inline');
  }, [workspace]);

  const saveWorkspace = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const updated = await workspaceData?.updateWorkspace?.({
        execution_mode: executionMode as any,
        execution_priority: executionPriority as any,
        expected_artifacts: parseList(expectedArtifacts),
        metadata: {
          ...(workspace?.metadata || {}),
          sgr_enabled: sgrEnabled,
          sgr_mode: sgrMode,
        },
      });
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspace?.id || ''}/playbook-auto-exec-config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook_code: 'intent_extraction',
          auto_execute: intentAutoExecute,
          confidence_threshold: intentThreshold,
        }),
      });
      if (!updated || !response.ok) {
        throw new Error('Save failed');
      }
      setMessage('Saved');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="workspace-settings-workspace-section">
      <Field label="Execution Mode">
        <select
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={executionMode}
          onChange={(event) => setExecutionMode(event.target.value)}
        >
          <option value="qa">QA</option>
          <option value="execution">Execution</option>
          <option value="hybrid">Hybrid</option>
          <option value="meeting">Meeting</option>
        </select>
      </Field>
      <Field label="Priority">
        <select
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={executionPriority}
          onChange={(event) => setExecutionPriority(event.target.value)}
        >
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </Field>
      <Field label="Expected Artifacts">
        <input
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={expectedArtifacts}
          onChange={(event) => setExpectedArtifacts(event.target.value)}
        />
      </Field>
      <label className="flex items-center gap-2 rounded border border-gray-200 p-2 text-sm dark:border-gray-800">
        <input
          type="checkbox"
          checked={intentAutoExecute}
          onChange={(event) => setIntentAutoExecute(event.target.checked)}
        />
        <span>Intent auto-execute</span>
      </label>
      {intentAutoExecute ? (
        <Field label={`Confidence ${intentThreshold.toFixed(1)}`}>
          <input
            className="w-full"
            type="range"
            min={0.5}
            max={1}
            step={0.1}
            value={intentThreshold}
            onChange={(event) => setIntentThreshold(Number(event.target.value))}
          />
        </Field>
      ) : null}
      <label className="flex items-center gap-2 rounded border border-gray-200 p-2 text-sm dark:border-gray-800">
        <input
          type="checkbox"
          checked={sgrEnabled}
          onChange={(event) => setSgrEnabled(event.target.checked)}
        />
        <span>SGR</span>
      </label>
      {sgrEnabled ? (
        <Field label="SGR Mode">
          <select
            className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
            value={sgrMode}
            onChange={(event) => setSgrMode(event.target.value === 'two_pass' ? 'two_pass' : 'inline')}
          >
            <option value="inline">Inline</option>
            <option value="two_pass">Two-pass</option>
          </select>
        </Field>
      ) : null}
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded bg-gray-900 px-3 py-2 text-sm font-semibold text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400 dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white"
        disabled={saving || !workspace}
        onClick={() => void saveWorkspace()}
      >
        <Save aria-hidden="true" className="h-4 w-4" />
        {saving ? 'Saving' : 'Save'}
      </button>
      {message ? <div className="text-xs text-gray-500 dark:text-gray-400">{message}</div> : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">{label}</span>
      {children}
    </label>
  );
}

function ExecutionSection({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  return <WorkspaceExecutionSettingsControls apiUrl={apiUrl} workspaceId={workspaceId} />;
}

function ToolEnginesSection({ workspaceId }: { workspaceId: string }) {
  const [toolOverlayOpen, setToolOverlayOpen] = useState(false);

  return (
    <div className="space-y-3" data-testid="workspace-settings-tools-section">
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex items-start gap-2">
          <Cpu aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold">Tool Engines</div>
            <div className="break-words text-gray-500 dark:text-gray-400">
              Pack-owned runtimes such as ComfyUI, Blender, Site-Hub, and cloud mesh services.
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => setToolOverlayOpen(true)}
      >
        <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
        Open Tool Overlay
      </button>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => openAppRouteInNewWindow(`/settings?tab=runtime&section=runtime-environments&workspace_id=${encodeURIComponent(workspaceId)}`)}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
        Open Tool Runtime Settings
      </button>
      <div data-testid="workspace-settings-tool-engine-extensions">
        <Suspense fallback={<div className="p-2 text-xs text-gray-500">Loading runtime extensions...</div>}>
          <CapabilityExtensionSlot section="runtime-environments" workspaceId={workspaceId} />
        </Suspense>
      </div>
      <WorkspaceToolOverlayFloatingPanel
        open={toolOverlayOpen}
        workspaceId={workspaceId}
        onClose={() => setToolOverlayOpen(false)}
      />
    </div>
  );
}

function DataSection({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const workspaceData = useWorkspaceDataOptional();
  const workspace = workspaceData?.workspace;
  const [dataSourcesOpen, setDataSourcesOpen] = useState(false);
  const toolConnections = useMemo(() => workspaceData?.systemStatus?.tools || {}, [workspaceData?.systemStatus?.tools]);
  const modalWorkspace = workspace
    ? {
      ...workspace,
      execution_mode: workspace.execution_mode || undefined,
      execution_priority: workspace.execution_priority || undefined,
    }
    : null;

  return (
    <div className="space-y-3" data-testid="workspace-settings-data-section">
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex items-start gap-2 py-1">
          <HardDrive aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold">Storage</div>
            <div className="break-words text-gray-500 dark:text-gray-400">{workspace?.storage_base_path || '-'}</div>
            <div className="break-words text-gray-500 dark:text-gray-400">{workspace?.artifacts_dir || 'artifacts'}</div>
          </div>
        </div>
        <div className="flex items-start gap-2 py-1">
          <PlayCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold">Artifacts</div>
            <div className="break-words text-gray-500 dark:text-gray-400">{formatList(workspace?.expected_artifacts) || '-'}</div>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => setDataSourcesOpen(true)}
      >
        <Database aria-hidden="true" className="h-4 w-4" />
        Open Data Sources
      </button>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => openAppRouteInNewWindow(`/workspaces/${workspaceId}/instruction`)}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
        Open Instructions
      </button>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => openAppRouteInNewWindow(`/settings?workspace_id=${encodeURIComponent(workspaceId)}`)}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
        Open System Settings
      </button>
      {dataSourcesOpen ? (
        <Suspense fallback={null}>
          <StoragePathConfigModal
            isOpen={dataSourcesOpen}
            onClose={() => setDataSourcesOpen(false)}
            workspace={modalWorkspace}
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            onSuccess={() => void workspaceData?.refreshWorkspaceDetails?.()}
            toolConnections={toolConnections}
          />
        </Suspense>
      ) : null}
    </div>
  );
}
