'use client';

import dynamic from 'next/dynamic';
import { useTools } from '../hooks/useTools';
import type { SettingsTab } from '../types';

interface SettingsContentHostProps {
  activeTab: SettingsTab;
  activeSection?: string;
  activeProvider?: string;
  workspaceId?: string;
  activeGroupId?: string;
  topologyRevision?: number;
  initialCatalogCategory?: string;
  onCredentialsNavigate: (section?: string, provider?: string) => void;
  onSendToAssistant: (message: string) => void;
}

function SettingsContentFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4 text-sm text-secondary dark:text-gray-400"
    >
      Loading...
    </div>
  );
}

const BasicSettingsPanel = dynamic(
  () => import('./BasicSettingsPanel').then((mod) => mod.BasicSettingsPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const CredentialsAndOAuthPanel = dynamic(
  () => import('./CredentialsAndOAuthPanel').then((mod) => mod.CredentialsAndOAuthPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const MindscapePanel = dynamic(
  () => import('./MindscapePanel').then((mod) => mod.MindscapePanel),
  { ssr: false, loading: SettingsContentFallback }
);
const SocialMediaPanel = dynamic(
  () => import('./SocialMediaPanel').then((mod) => mod.SocialMediaPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const ToolsPanel = dynamic(
  () => import('./ToolsPanel').then((mod) => mod.ToolsPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const LocalizationPanel = dynamic(
  () => import('./LocalizationPanel').then((mod) => mod.LocalizationPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const ServiceStatusPanel = dynamic(
  () => import('./ServiceStatusPanel').then((mod) => mod.ServiceStatusPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const PacksPanel = dynamic(
  () => import('./PacksPanel').then((mod) => mod.PacksPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const GovernancePanel = dynamic(
  () => import('./GovernancePanel').then((mod) => mod.GovernancePanel),
  { ssr: false, loading: SettingsContentFallback }
);
const AITeamGovernancePanel = dynamic(
  () => import('./panels/AITeamGovernancePanel').then((mod) => mod.AITeamGovernancePanel),
  { ssr: false, loading: SettingsContentFallback }
);
const RuntimeEnvironmentsSettings = dynamic(
  () => import('./panels/RuntimeEnvironmentsSettings').then((mod) => mod.RuntimeEnvironmentsSettings),
  { ssr: false, loading: SettingsContentFallback }
);
const DeviceLinkReadinessPanel = dynamic(
  () => import('./panels/DeviceLinkReadinessPanel').then((mod) => mod.DeviceLinkReadinessPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const HostResourcesPanel = dynamic(
  () => import('./panels/HostResourcesPanel').then((mod) => mod.HostResourcesPanel),
  { ssr: false, loading: SettingsContentFallback }
);
const RemoteWorkbenchAccessSettings = dynamic(
  () => import('./panels/RemoteWorkbenchAccessSettings').then((mod) => mod.RemoteWorkbenchAccessSettings),
  { ssr: false, loading: SettingsContentFallback }
);
const WorkspaceProductConfigurationPanel = dynamic(
  () => import('./panels/WorkspaceProductConfigurationPanel').then((mod) => mod.WorkspaceProductConfigurationPanel),
  { ssr: false, loading: SettingsContentFallback }
);

function PacksSettingsContent({ activeSection }: { activeSection?: string }) {
  const { getToolStatusForPack } = useTools();
  return <PacksPanel getToolStatus={getToolStatusForPack} activeSection={activeSection || 'packages'} />;
}

export function SettingsContentHost({
  activeTab,
  activeSection,
  activeProvider,
  workspaceId,
  activeGroupId,
  topologyRevision,
  initialCatalogCategory,
  onCredentialsNavigate,
  onSendToAssistant,
}: SettingsContentHostProps) {
  switch (activeTab) {
    case 'basic':
      return (
        <BasicSettingsPanel
          activeSection={activeSection}
          workspaceId={workspaceId}
          initialCatalogCategory={initialCatalogCategory}
        />
      );
    case 'credentials':
      return (
        <CredentialsAndOAuthPanel
          activeSection={activeSection}
          activeProvider={activeProvider}
          onNavigate={onCredentialsNavigate}
        />
      );
    case 'mindscape':
      return <MindscapePanel />;
    case 'ai-team-governance':
      return <AITeamGovernancePanel activeSection={activeSection} onSendToAssistant={onSendToAssistant} />;
    case 'social_media':
      return <SocialMediaPanel activeProvider={activeProvider} workspaceId={workspaceId} />;
    case 'tools':
      return <ToolsPanel activeSection={activeSection} activeProvider={activeProvider} />;
    case 'runtime':
      if (
        activeSection === 'host-resources'
        || activeSection === 'host-resources-observability'
        || activeSection === 'workspace-resource-allocations'
      ) {
        return <HostResourcesPanel activeSection={activeSection} workspaceId={workspaceId} />;
      }
      if (activeSection === 'device-link-readiness') {
        return <DeviceLinkReadinessPanel workspaceId={workspaceId} />;
      }
      return <RuntimeEnvironmentsSettings />;
    case 'remote_workbench_access':
      return <RemoteWorkbenchAccessSettings />;
    case 'localization':
      return <LocalizationPanel activeSection={activeSection} />;
    case 'service_status':
      return <ServiceStatusPanel />;
    case 'packs_status':
      return <PacksSettingsContent activeSection={activeSection} />;
    case 'workspace_products':
      return (
        <WorkspaceProductConfigurationPanel
          workspaceId={workspaceId}
          activeGroupId={activeGroupId}
          topologyRevision={topologyRevision}
        />
      );
    case 'governance':
      return <GovernancePanel activeSection={activeSection} />;
    default:
      return (
        <BasicSettingsPanel
          activeSection={activeSection}
          workspaceId={workspaceId}
          initialCatalogCategory={initialCatalogCategory}
        />
      );
  }
}
