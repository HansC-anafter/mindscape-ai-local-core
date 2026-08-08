'use client';

import React, { Suspense, useMemo, useState } from 'react';
import {
  Cpu,
  Database,
  ExternalLink,
  HardDrive,
  PlayCircle,
  Share2,
  SlidersHorizontal,
} from 'lucide-react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import { WorkspaceExecutionSettingsControls } from '@/components/workspace/WorkspaceExecutionSettingsControls';
import { WorkspaceToolOverlayFloatingPanel } from '@/components/workspace/WorkspaceToolOverlayFloatingPanel';
import { formatList } from './WorkspaceSettingsToolPanelUtils';

const CapabilityExtensionSlot = React.lazy(() => import('../components/CapabilityExtensionSlot'));
const StoragePathConfigModal = React.lazy(() => import('@/components/StoragePathConfigModal'));

export {
  WorkspaceMembersAccessSection as MembersAccessSection,
} from './workspaceSettingsSections/WorkspaceMembersAccessSection';

export function ExecutionSection({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  return <WorkspaceExecutionSettingsControls apiUrl={apiUrl} workspaceId={workspaceId} />;
}

export function ToolEnginesSection({ workspaceId }: { workspaceId: string }) {
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

export function SocialMediaSection({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="space-y-3" data-testid="workspace-settings-social-section">
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex items-start gap-2">
          <Share2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold">Social Media</div>
            <div className="break-words text-gray-500 dark:text-gray-400">
              Workspace-scoped provider credentials and reference intake settings.
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={() => openAppRouteInNewWindow(`/settings?tab=social_media&provider=youtube&configure=1&workspace_id=${encodeURIComponent(workspaceId)}`)}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
        Open YouTube Workspace Settings
      </button>
      <div data-testid="workspace-settings-social-media-extensions">
        <Suspense fallback={<div className="p-2 text-xs text-gray-500">Loading social media extensions...</div>}>
          <CapabilityExtensionSlot section="social-media:youtube" workspaceId={workspaceId} />
        </Suspense>
      </div>
    </div>
  );
}

export function DataSection({
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
