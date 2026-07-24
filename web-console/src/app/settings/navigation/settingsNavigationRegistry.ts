import type { ComponentType, SVGProps } from 'react';
import Activity from 'lucide-react/dist/esm/icons/activity.js';
import Brain from 'lucide-react/dist/esm/icons/brain.js';
import KeyRound from 'lucide-react/dist/esm/icons/key-round.js';
import Languages from 'lucide-react/dist/esm/icons/languages.js';
import Package from 'lucide-react/dist/esm/icons/package.js';
import PlayCircle from 'lucide-react/dist/esm/icons/play-circle.js';
import SettingsIcon from 'lucide-react/dist/esm/icons/settings.js';
import Share2 from 'lucide-react/dist/esm/icons/share-2.js';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check.js';
import UsersRound from 'lucide-react/dist/esm/icons/users-round.js';
import Wrench from 'lucide-react/dist/esm/icons/wrench.js';
import type { SettingsTab } from '../types';

export type NavigationIcon = ComponentType<SVGProps<SVGSVGElement>>;

export interface NavigationItem {
  id: string;
  label: string;
  icon?: NavigationIcon;
  tab: SettingsTab;
  section?: string;
  provider?: string;
  model?: string;
  service?: string;
  mobileOrder?: number;
  children?: NavigationItem[];
}

export interface NavigationMatchContext {
  activeTab: SettingsTab;
  activeSection?: string;
  activeProvider?: string;
  activeModel?: string;
  activeService?: string;
}

export const navigationItems: NavigationItem[] = [
  {
    id: 'basic',
    label: 'basicSettings',
    icon: SettingsIcon,
    tab: 'basic',
    mobileOrder: 0,
    children: [
      { id: 'backend-mode', label: 'backendMode', tab: 'basic', section: 'backend-mode' },
      { id: 'keyboard-shortcuts', label: 'keyboardShortcuts', tab: 'basic', section: 'keyboard-shortcuts' },
      { id: 'language-preference', label: 'languagePreference', tab: 'basic', section: 'language-preference' },
      { id: 'models-and-quota', label: 'modelsAndQuota', tab: 'basic', section: 'models-and-quota' },
      { id: 'model-routing-registry', label: 'modelRoutingRegistry', tab: 'basic', section: 'model-routing-registry' },
      { id: 'theme-preset', label: 'themePreset', tab: 'basic', section: 'theme-preset' },
      { id: 'cloud-extension', label: 'cloudExtension', tab: 'basic', section: 'cloud-extension' },
      { id: 'unsplash-fingerprints', label: 'unsplashFingerprints', tab: 'basic', section: 'unsplash-fingerprints' },
      { id: 'port-configuration', label: 'portConfiguration', tab: 'basic', section: 'port-configuration' },
      { id: 'runtime-backup', label: 'localRuntimeBackup', tab: 'basic', section: 'runtime-backup' },
    ],
  },
  {
    id: 'credentials',
    label: 'credentialsAndOAuth',
    icon: KeyRound,
    tab: 'credentials',
    mobileOrder: 1,
    children: [
      { id: 'service-credentials', label: 'serviceCredentials', tab: 'credentials', section: 'service-credentials' },
      { id: 'oauth-integrations', label: 'oauthIntegration', tab: 'credentials', section: 'oauth-integrations' },
    ],
  },
  { id: 'mindscape', label: 'mindscapeConfiguration', icon: Brain, tab: 'mindscape', mobileOrder: 2 },
  {
    id: 'ai-team-governance',
    label: 'aiTeamGovernance',
    icon: UsersRound,
    tab: 'ai-team-governance',
    children: [
      { id: 'install-agents', label: 'installAgents', tab: 'ai-team-governance', section: 'install-agents' },
      { id: 'installed-agents', label: 'installedAgents', tab: 'ai-team-governance', section: 'installed-agents' },
      { id: 'model-policy', label: 'modelPolicy', tab: 'ai-team-governance', section: 'model-policy' },
      { id: 'network-policy', label: 'networkPolicy', tab: 'ai-team-governance', section: 'network-policy' },
      { id: 'secrets-policy', label: 'secretsPolicy', tab: 'ai-team-governance', section: 'secrets-policy' },
    ],
  },
  {
    id: 'runtime',
    label: 'runtimeEnvironments',
    icon: PlayCircle,
    tab: 'runtime',
    mobileOrder: 8,
    children: [
      { id: 'runtime-environments', label: 'runtimeEnvironments', tab: 'runtime', section: 'runtime-environments' },
      { id: 'device-link-readiness', label: 'Device Link', tab: 'runtime', section: 'device-link-readiness' },
      { id: 'host-resources', label: 'hostResources', tab: 'runtime', section: 'host-resources' },
      { id: 'workspace-resource-allocations', label: 'workspaceResourceAllocations', tab: 'runtime', section: 'workspace-resource-allocations' },
      { id: 'host-resources-observability', label: 'hostResourceObservability', tab: 'runtime', section: 'host-resources-observability' },
    ],
  },
  {
    id: 'remote-workbench-access',
    label: 'remoteWorkbenchAccess',
    icon: ShieldCheck,
    tab: 'remote_workbench_access',
    mobileOrder: 9,
  },
  {
    id: 'tools',
    label: 'toolsAndIntegrations',
    icon: Wrench,
    tab: 'tools',
    children: [
      { id: 'system-tools', label: 'systemTools', tab: 'tools', section: 'system-tools' },
      { id: 'external-saas-tools', label: 'externalSAASTools', tab: 'tools', section: 'external-saas-tools' },
      { id: 'developer-integrations', label: 'developerIntegrations', tab: 'tools', section: 'developer-integrations' },
      {
        id: 'mcp-server',
        label: 'mcpServer',
        tab: 'tools',
        section: 'mcp-server',
        children: [
          { id: 'mcp-openai', label: 'OpenAI', tab: 'tools', section: 'mcp-server', provider: 'openai' },
          { id: 'mcp-anthropic', label: 'Anthropic', tab: 'tools', section: 'mcp-server', provider: 'anthropic' },
          { id: 'mcp-github', label: 'GitHub', tab: 'tools', section: 'mcp-server', provider: 'github' },
          { id: 'mcp-google', label: 'Google', tab: 'tools', section: 'mcp-server', provider: 'google' },
          { id: 'mcp-custom', label: 'customMCP', tab: 'tools', section: 'mcp-server', provider: 'custom' },
        ],
      },
      {
        id: 'third-party-workflow',
        label: 'thirdPartyWorkflow',
        tab: 'tools',
        section: 'third-party-workflow',
        children: [
          { id: 'workflow-zapier', label: 'Zapier', tab: 'tools', section: 'third-party-workflow', provider: 'zapier' },
          { id: 'workflow-n8n', label: 'n8n', tab: 'tools', section: 'third-party-workflow', provider: 'n8n' },
          { id: 'workflow-make', label: 'Make', tab: 'tools', section: 'third-party-workflow', provider: 'make' },
          { id: 'workflow-integromat', label: 'Integromat', tab: 'tools', section: 'third-party-workflow', provider: 'integromat' },
          { id: 'workflow-custom', label: 'customWorkflow', tab: 'tools', section: 'third-party-workflow', provider: 'custom' },
        ],
      },
    ],
  },
  {
    id: 'social_media',
    label: 'socialMediaIntegration',
    icon: Share2,
    tab: 'social_media',
    mobileOrder: 3,
    children: [
      { id: 'twitter', label: 'twitterIntegration', tab: 'social_media', provider: 'twitter' },
      { id: 'facebook', label: 'facebookIntegration', tab: 'social_media', provider: 'facebook' },
      { id: 'instagram', label: 'instagramIntegration', tab: 'social_media', provider: 'instagram' },
      { id: 'linkedin', label: 'linkedinIntegration', tab: 'social_media', provider: 'linkedin' },
      { id: 'youtube', label: 'youtubeIntegration', tab: 'social_media', provider: 'youtube' },
      { id: 'line', label: 'lineIntegration', tab: 'social_media', provider: 'line' },
    ],
  },
  {
    id: 'localization',
    label: 'localization',
    icon: Languages,
    tab: 'localization',
    mobileOrder: 4,
    children: [
      { id: 'auto-translation', label: 'autoTranslation', tab: 'localization', section: 'auto-translation' },
      { id: 'translation-management', label: 'translationManagement', tab: 'localization', section: 'translation-management' },
    ],
  },
  {
    id: 'workspace-products',
    label: 'workspaceProducts',
    icon: Package,
    tab: 'workspace_products',
    mobileOrder: 5,
  },
  {
    id: 'governance',
    label: 'governance',
    icon: ShieldCheck,
    tab: 'governance',
    mobileOrder: 7,
    children: [
      { id: 'node-governance', label: 'nodeGovernance', tab: 'governance', section: 'node' },
      { id: 'preflight', label: 'preflight', tab: 'governance', section: 'preflight' },
      { id: 'governance-mode', label: 'governanceMode', tab: 'governance', section: 'mode' },
      { id: 'cost-governance', label: 'costGovernance', tab: 'governance', section: 'cost' },
      { id: 'policy-service', label: 'policyService', tab: 'governance', section: 'policy' },
    ],
  },
  {
    id: 'packs_status',
    label: 'capabilityPacks',
    icon: Package,
    tab: 'packs_status',
    mobileOrder: 6,
    children: [
      { id: 'capability-packages', label: 'capabilityPackages', tab: 'packs_status', section: 'packages' },
      { id: 'capability-suites', label: 'capabilitySuites', tab: 'packs_status', section: 'suites' },
    ],
  },
  { id: 'service_status', label: 'serviceStatus', icon: Activity, tab: 'service_status', mobileOrder: 10 },
];

export const validSettingsTabs: readonly SettingsTab[] = navigationItems.map((item) => item.tab);

function hasMobileOrder(item: NavigationItem): item is NavigationItem & { mobileOrder: number } {
  return Number.isInteger(item.mobileOrder);
}

export const mobileNavigationItems: readonly NavigationItem[] = navigationItems
  .filter(hasMobileOrder)
  .sort((left, right) => left.mobileOrder - right.mobileOrder);

export function navigationItemMatches(
  item: NavigationItem,
  context: NavigationMatchContext,
): boolean {
  if (item.tab !== context.activeTab) return false;
  if (item.section !== undefined && item.section !== context.activeSection) return false;
  if (item.section === undefined && context.activeSection) {
    return Boolean(item.children?.some((child) => navigationItemMatches(child, context)));
  }
  if (item.provider !== undefined && item.provider !== context.activeProvider) return false;
  if (item.service !== undefined && item.service !== context.activeService) return false;
  if (item.model !== undefined && item.model !== context.activeModel) return false;
  if (item.provider === undefined && context.activeProvider) return false;
  if (item.service === undefined && context.activeService) return false;
  if (item.model === undefined && context.activeModel) return false;
  return true;
}

export function activeExpandableItemIds(context: NavigationMatchContext): string[] {
  const ids: string[] = [];
  const visit = (items: NavigationItem[], parentId?: string) => {
    items.forEach((item) => {
      const childMatches = item.children?.some((child) => navigationItemMatches(child, context));
      if (childMatches || navigationItemMatches(item, context)) {
        if (parentId) ids.push(parentId);
        if (item.children?.length) ids.push(item.id);
      }
      if (item.children?.length) {
        visit(item.children, item.id);
      }
    });
  };
  visit(navigationItems);
  return Array.from(new Set(ids));
}
