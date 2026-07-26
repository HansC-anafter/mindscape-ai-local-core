'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useT } from '../../../../lib/i18n';
import { ToolCard } from '../ToolCard';
import { ToolGrid } from '../ToolGrid';
import { Section } from '../Section';
import { ExternalSettingsEmbed } from './ExternalSettingsEmbed';
import { AddRuntimeModal } from './AddRuntimeModal';
import { HostResourcesPanel } from './HostResourcesPanel';
import { showNotification } from '../../hooks/useSettingsNotification';
import { BaseModal } from '../../../../components/BaseModal';
import { getApiBaseUrl } from '../../../../lib/api-url';
import { createRuntimeSettingsExtensionComponent } from './runtimeEnvironmentsSettings/extensionComponent';
import { GeminiCliSettingsForm } from './runtimeEnvironmentsSettings/GeminiCliSettingsForm';
import {
  resolveRuntimeModalPanels,
  shouldRenderSettingsPanelInline,
  shouldRenderWorkflowPanelInline,
} from './runtimeEnvironmentsSettings/panelMatching';
import { SiteHubSettingsForm } from './runtimeEnvironmentsSettings/SiteHubSettingsForm';
import type {
  RuntimeEnvironment,
  RuntimeSettingsExtensionProps,
  SettingsPanel,
} from './runtimeEnvironmentsSettings/types';

export { createRuntimeSettingsExtensionComponent } from './runtimeEnvironmentsSettings/extensionComponent';
export {
  resolveRuntimeModalPanels,
  shouldRenderSettingsPanelInline,
} from './runtimeEnvironmentsSettings/panelMatching';
export type {
  RuntimeEnvironment,
  RuntimeSettingsExtensionProps,
  SettingsPanel,
} from './runtimeEnvironmentsSettings/types';

export function RuntimeEnvironmentsSettings() {
  const t = useT();
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [selectedRuntime, setSelectedRuntime] = useState<string | null>(null);
  const [showAddRuntimeModal, setShowAddRuntimeModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [settingsPanels, setSettingsPanels] = useState<SettingsPanel[]>([]);
  const [workflowPanels, setWorkflowPanels] = useState<SettingsPanel[]>([]);
  const apiBaseUrl = getApiBaseUrl();

  useEffect(() => {
    loadRuntimes();
    loadSettingsPanels();
    loadWorkflowPanels();

    // Listen for OAuth popup result
    const handleOAuthMessage = (event: MessageEvent) => {
      if (event.data?.type === 'RUNTIME_OAUTH_RESULT') {
        loadRuntimes(); // Refresh to pick up new auth_status
      }
    };
    window.addEventListener('message', handleOAuthMessage);
    return () => window.removeEventListener('message', handleOAuthMessage);
  }, []);

  const loadSettingsPanels = async () => {
    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/settings/extensions?section=runtime-environments`
      );
      if (response.ok) {
        const data = await response.json();
        const panels: SettingsPanel[] = data.map((ext: any) => ({
          capabilityCode: ext.capability_code,
          componentCode: ext.component_code,
          section: 'runtime-environments',
          title: ext.title,
          description: ext.description,
          displayMode: ext.display_mode,
          requiresWorkspaceId: ext.requires_workspace_id,
          showWhen: ext.show_when ? {
            runtimeCodes: ext.show_when.runtime_codes,
          } : undefined,
          propsSchema: ext.props_schema,
          importPath: ext.import_path,
          export: ext.export || 'default',
          path: ext.path,
          assetUrl: ext.asset_url,
          integrity: ext.integrity,
          runtime: ext.runtime,
          legacyContext: ext.legacy_context,
          bytes: ext.bytes,
          assetPath: ext.asset_path,
        }));
        setSettingsPanels(panels);
      } else {
        console.error('Failed to load runtime settings panels:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('Failed to load runtime settings panels:', error);
    }
  };

  const loadWorkflowPanels = async () => {
    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/settings/extensions?section=workflow-engines`
      );
      if (response.ok) {
        const data = await response.json();
        const panels: SettingsPanel[] = data.map((ext: any) => ({
          capabilityCode: ext.capability_code,
          componentCode: ext.component_code,
          section: 'workflow-engines',
          title: ext.title,
          description: ext.description,
          displayMode: ext.display_mode,
          requiresWorkspaceId: ext.requires_workspace_id,
          showWhen: ext.show_when ? {
            runtimeCodes: ext.show_when.runtime_codes,
          } : undefined,
          propsSchema: ext.props_schema,
          importPath: ext.import_path,
          export: ext.export || 'default',
          path: ext.path,
          assetUrl: ext.asset_url,
          integrity: ext.integrity,
          runtime: ext.runtime,
          legacyContext: ext.legacy_context,
          bytes: ext.bytes,
          assetPath: ext.asset_path,
        }));
        setWorkflowPanels(panels);
      }
    } catch (error) {
      console.error('Failed to load workflow panels:', error);
    }
  };

  const loadExtensionComponent = createRuntimeSettingsExtensionComponent;

  const getRuntimeCodes = () => {
    return runtimes.map(r => r.id);
  };

  const loadRuntimes = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/runtime-environments');
      if (response.ok) {
        const data = await response.json();
        const runtimesList = data.runtimes || [];
        setRuntimes(runtimesList);
      } else {
        // Fallback to default (Local-Core only)
        const defaultRuntimes: RuntimeEnvironment[] = [
          {
            id: 'local-core',
            name: 'Local-Core Runtime',
            description: 'Local execution environment, enabled by default',
            icon: 'desktop',
            status: 'active',
            isDefault: true,
            supportsDispatch: true,
            supportsCell: true,
          },
        ];
        setRuntimes(defaultRuntimes);
      }
    } catch (error) {
      console.error('Failed to load runtimes:', error);
      showNotification('error', 'Failed to load runtime environments');
    } finally {
      setLoading(false);
    }
  };

  const getStatusInfo = (runtime: RuntimeEnvironment) => {
    if (runtime.isDefault) {
      return { status: 'connected' as const, label: t('default' as any) || 'Default', icon: 'check' };
    }
    // Show OAuth auth_status badge when available
    if (runtime.auth_type === 'oauth2' && runtime.auth_status) {
      switch (runtime.auth_status) {
        case 'connected':
          return {
            status: 'connected' as const,
            label: runtime.auth_identity ? `Connected as ${runtime.auth_identity}` : 'Connected',
            icon: 'check',
          };
        case 'pending':
          return { status: 'not_configured' as const, label: 'Connecting...', icon: 'pending' };
        case 'error':
          return { status: 'inactive' as const, label: 'Auth Error', icon: 'cross' };
        case 'disconnected':
          return { status: 'not_configured' as const, label: 'Not Connected', icon: 'warning' };
      }
    }
    switch (runtime.status) {
      case 'active':
        return { status: 'connected' as const, label: t('enabled' as any) || 'Enabled', icon: 'check' };
      case 'configured':
        return { status: 'connected' as const, label: t('configured' as any) || 'Configured', icon: 'gear' };
      case 'not_configured':
        return { status: 'not_configured' as const, label: t('notConfigured' as any) || 'Not Configured', icon: 'warning' };
      default:
        return { status: 'inactive' as const, label: t('disabled' as any) || 'Disabled', icon: 'cross' };
    }
  };

  const getRuntimeConfigPath = (runtimeId: string): string => {
    // Use backend proxy path instead of direct config_url
    return `/api/v1/runtime-proxy/${runtimeId}/settings`;
  };

  if (loading) {
    return <div className="text-sm text-gray-500 dark:text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <Section
        title={t('runtimeEnvironments' as any) || 'Runtime Environments'}
        description={t('runtimeEnvironmentsDescription' as any) || 'Configure execution environments for running playbooks and processing tasks'}
      >
        <ToolGrid>
          {runtimes.map((runtime) => {
            const statusInfo = getStatusInfo(runtime);
            return (
              <div key={runtime.id}>
                <ToolCard
                  toolType={runtime.id}
                  name={runtime.name}
                  description={runtime.description}
                  icon={runtime.icon}
                  status={statusInfo}
                  onConfigure={
                    runtime.isDefault
                      ? () => { } // No-op for default runtime
                      : () => setSelectedRuntime(runtime.id)
                  }
                >
                  {/* OAuth Connect / Disconnect buttons */}
                  {!runtime.isDefault && runtime.auth_type === 'oauth2' && (
                    <div className="mt-2 flex gap-2">
                      {runtime.auth_status === 'connected' ? (
                        <button
                          type="button"
                          onClick={async (e) => {
                            e.stopPropagation();
                            const apiUrl = getApiBaseUrl();
                            try {
                              await fetch(
                                `${apiUrl}/api/v1/runtime-oauth/${runtime.id}/disconnect`,
                                { method: 'POST' }
                              );
                              loadRuntimes();
                            } catch (err) {
                              console.error('Disconnect failed:', err);
                            }
                          }}
                          className="text-xs px-3 py-1 rounded-md border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                        >
                          Disconnect
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            const apiUrl = getApiBaseUrl();
                            const w = 500, h = 600;
                            const left = window.screenX + (window.innerWidth - w) / 2;
                            const top = window.screenY + (window.innerHeight - h) / 2;
                            window.open(
                              `${apiUrl}/api/v1/runtime-oauth/${runtime.id}/authorize`,
                              'oauth-popup',
                              `width=${w},height=${h},left=${left},top=${top},popup=true`
                            );
                          }}
                          className="text-xs px-3 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                        >
                          Connect with Google
                        </button>
                      )}
                    </div>
                  )}
                </ToolCard>
              </div>
            );
          })}

          {/* Add Runtime button */}
          <ToolCard
            toolType="add-runtime"
            name={t('addRuntime' as any) || 'Add Runtime Environment'}
            description={t('addRuntimeDescription' as any) || 'Add a custom runtime execution environment'}
            icon="+"
            status={{ status: 'not_configured', label: t('add' as any) || 'Add', icon: '+' }}
            onConfigure={() => setShowAddRuntimeModal(true)}
          />
        </ToolGrid>
      </Section>

      {/* Runtime Configuration Modal */}
      {selectedRuntime && (() => {
        const runtime = runtimes.find(r => r.id === selectedRuntime);
        const runtimeModalPanels = resolveRuntimeModalPanels(runtime, [...settingsPanels, ...workflowPanels]);
        const primaryRuntimeModalPanel = runtimeModalPanels[0] || null;
        const isSiteHub = selectedRuntime === 'site-hub' || runtime?.config_url?.includes('anafter.co');
        const isGcaLocal = selectedRuntime === 'gca-local';
        return (
          <BaseModal
            isOpen={true}
            onClose={() => setSelectedRuntime(null)}
            title={
              isGcaLocal
                ? 'GCA Auth - OAuth Credentials'
                : (runtime?.name || primaryRuntimeModalPanel?.title || t('runtimeConfiguration' as any) || 'Runtime Configuration')
            }
            maxWidth={isGcaLocal ? 'max-w-lg' : 'max-w-[92vw]'}
          >
            {isGcaLocal ? (
              <GeminiCliSettingsForm
                onSave={() => {
                  setSelectedRuntime(null);
                  loadRuntimes();
                  showNotification('success', 'GCA OAuth credentials updated');
                }}
                onCancel={() => setSelectedRuntime(null)}
              />
            ) : runtimeModalPanels.length ? (
              <div className="space-y-6">
                {runtimeModalPanels.map((runtimeModalPanel) => {
                  const RuntimePanelComponent = loadExtensionComponent(runtimeModalPanel);
                  return (
                    <Section
                      key={`${runtimeModalPanel.capabilityCode}:${runtimeModalPanel.componentCode}:${runtimeModalPanel.section || 'runtime'}`}
                      title={runtimeModalPanel.title}
                      description={runtimeModalPanel.description}
                    >
                      <Suspense fallback={
                        <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                          {t('loading' as any) || 'Loading'} {runtimeModalPanel.title}...
                        </div>
                      }>
                        <RuntimePanelComponent runtimeId={selectedRuntime} runtime={runtime} apiUrl={apiBaseUrl} />
                      </Suspense>
                    </Section>
                  );
                })}
              </div>
            ) : isSiteHub ? (
              <SiteHubSettingsForm
                runtime={runtime!}
                onSave={() => {
                  setSelectedRuntime(null);
                  loadRuntimes();
                  showNotification('success', t('runtimeConfigurationUpdated' as any) || 'Runtime configuration updated');
                }}
                onCancel={() => setSelectedRuntime(null)}
              />
            ) : (
              <ExternalSettingsEmbed
                title={runtime?.name || t('runtimeConfiguration' as any) || 'Runtime Configuration'}
                description={runtime?.description || ''}
                embedPath={getRuntimeConfigPath(selectedRuntime)}
                height="700px"
                onMessage={(event) => {
                  if (event.data.type === 'RUNTIME_CONFIG_UPDATED') {
                    setSelectedRuntime(null);
                    loadRuntimes();
                    showNotification('success', t('runtimeConfigurationUpdated' as any) || 'Runtime configuration updated');
                  }
                }}
              />
            )}
          </BaseModal>
        );
      })()}

      {/* Add Runtime Modal */}
      {showAddRuntimeModal && (
        <AddRuntimeModal
          isOpen={true}
          onClose={() => setShowAddRuntimeModal(false)}
          onSuccess={(newRuntime) => {
            setRuntimes([...runtimes, newRuntime]);
            setShowAddRuntimeModal(false);
            showNotification('success', t('runtimeAddedSuccessfully' as any, { name: newRuntime.name }) || `Runtime "${newRuntime.name}" added successfully`);
            loadSettingsPanels(); // Reload panels after runtime added
          }}
        />
      )}

      <HostResourcesPanel />

      {/* Dynamic Settings Panels (Capability Slot) */}
      {settingsPanels.map((panel) => {
        if (!shouldRenderSettingsPanelInline(panel)) {
          return null;
        }
        // Check showWhen conditions
        if (panel.showWhen?.runtimeCodes) {
          const runtimeCodes = getRuntimeCodes();
          const hasRequiredRuntime = panel.showWhen.runtimeCodes.some(
            code => runtimeCodes.includes(code)
          );
          if (!hasRequiredRuntime) {
            return null;
          }
        }

        const ExtensionComponent = loadExtensionComponent(panel);
        const props: RuntimeSettingsExtensionProps = { ...panel.propsSchema, apiUrl: apiBaseUrl };

        // Add workspaceId if required
        if (panel.requiresWorkspaceId) {
          const workspaceId = typeof window !== 'undefined'
            ? window.location.pathname.match(/\/workspaces\/([^\/]+)/)?.[1]
            : null;
          if (workspaceId) {
            props.workspaceId = workspaceId;
          } else {
            console.warn('Runtime settings panel requires workspaceId but none was found:', panel.componentCode);
          }
        }

        return (
          <Section
            key={`${panel.capabilityCode}:${panel.componentCode}`}
            title={panel.title}
            description={panel.description}
          >
            <Suspense fallback={
              <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                {t('loading' as any) || 'Loading'} {panel.title}...
              </div>
            }>
              <ExtensionComponent {...props} />
            </Suspense>
          </Section>
        );
      })}

      {/* Workflow Engines (third-party workflow tools like ComfyUI) */}
      {workflowPanels.length > 0 && (
        <>
          {workflowPanels.map((panel) => {
            if (!shouldRenderWorkflowPanelInline(panel, runtimes)) {
              return null;
            }
            const ExtensionComponent = loadExtensionComponent(panel);
            const props: RuntimeSettingsExtensionProps = { ...panel.propsSchema, apiUrl: apiBaseUrl };

            return (
              <Section
                key={`${panel.capabilityCode}:${panel.componentCode}`}
                title={panel.title}
                description={panel.description}
              >
                <Suspense fallback={
                  <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                    {t('loading' as any) || 'Loading'} {panel.title}...
                  </div>
                }>
                  <ExtensionComponent {...props} />
                </Suspense>
              </Section>
            );
          })}
        </>
      )}

    </div>
  );
}
