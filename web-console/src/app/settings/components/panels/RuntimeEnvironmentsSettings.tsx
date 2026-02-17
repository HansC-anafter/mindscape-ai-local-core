'use client';

import React, { useState, useEffect, Suspense, lazy } from 'react';
import { t } from '../../../../lib/i18n';
import { ToolCard } from '../ToolCard';
import { ToolGrid } from '../ToolGrid';
import { Section } from '../Section';
import { ExternalSettingsEmbed } from './ExternalSettingsEmbed';
import { AddRuntimeModal } from './AddRuntimeModal';
import { showNotification } from '../../hooks/useSettingsNotification';
import { BaseModal } from '../../../../components/BaseModal';
import { convertImportPathToContextKey, normalizeCapabilityContextKey } from '../../../../lib/capability-path';
import { getApiBaseUrl } from '../../../../lib/api-url';
// Use require.context to load capability components (webpack feature)
// Wrapped in try-catch: directory may be empty on fresh installs
let rawCapabilityComponentsContext: any;
try {
  // @ts-ignore - require.context is a webpack feature, not standard TypeScript
  rawCapabilityComponentsContext = require.context('../../../capabilities', true, /\.tsx$/, 'sync');
} catch {
  // Capabilities directory empty or missing — provide no-op fallback
  rawCapabilityComponentsContext = Object.assign(
    (() => ({})) as any,
    { keys: () => [] as string[], resolve: (k: string) => k, id: '' }
  );
}
const capabilityComponentKeys = new Set<string>(
  typeof rawCapabilityComponentsContext.keys === 'function'
    ? rawCapabilityComponentsContext.keys()
    : []
);
const capabilityComponentsContext = ((key: string) => {
  const normalizedKey = normalizeCapabilityContextKey(key);
  const resolvedKey = normalizedKey && capabilityComponentKeys.has(normalizedKey)
    ? normalizedKey
    : key;
  return rawCapabilityComponentsContext(resolvedKey);
}) as typeof rawCapabilityComponentsContext;

interface RuntimeEnvironment {
  id: string;
  name: string;
  description: string;
  icon: string;
  status: 'active' | 'inactive' | 'configured' | 'not_configured';
  isDefault?: boolean;
  is_default?: boolean;
  config_url?: string;
  auth_type?: string;
  auth_status?: 'disconnected' | 'pending' | 'connected' | 'error';
  auth_identity?: string | null;
  metadata?: Record<string, any>;
  supportsDispatch?: boolean;
  supportsCell?: boolean;
  recommendedForDispatch?: boolean;
}

interface SettingsPanel {
  capabilityCode: string;
  componentCode: string;
  title: string;
  description?: string;
  requiresWorkspaceId?: boolean;
  showWhen?: {
    runtimeCodes?: string[];
  };
  propsSchema?: Record<string, any>;
  importPath: string;
  export: string;
}

export function RuntimeEnvironmentsSettings() {
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [selectedRuntime, setSelectedRuntime] = useState<string | null>(null);
  const [showAddRuntimeModal, setShowAddRuntimeModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [settingsPanels, setSettingsPanels] = useState<SettingsPanel[]>([]);
  const [workflowPanels, setWorkflowPanels] = useState<SettingsPanel[]>([]);

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
        console.log('[Site-Hub Debug] Settings panels loaded:', data);
        setSettingsPanels(data);
      } else {
        console.error('[Site-Hub Debug] Failed to load settings panels:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('[Site-Hub Debug] Failed to load settings panels:', error);
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
          title: ext.title,
          description: ext.description,
          requiresWorkspaceId: ext.requires_workspace_id,
          showWhen: ext.show_when ? {
            runtimeCodes: ext.show_when.runtime_codes,
          } : undefined,
          propsSchema: ext.props_schema,
          importPath: ext.import_path,
          export: ext.export || 'default',
        }));
        setWorkflowPanels(panels);
      }
    } catch (error) {
      console.error('Failed to load workflow panels:', error);
    }
  };

  const loadExtensionComponent = (panel: SettingsPanel) => {
    const rawContextKey = convertImportPathToContextKey(panel.importPath);
    const contextKey = normalizeCapabilityContextKey(rawContextKey);

    return lazy(async () => {
      if (!contextKey || !capabilityComponentKeys.has(contextKey)) {
        return { default: () => null };
      }

      try {
        const moduleLoader = capabilityComponentsContext(contextKey);
        const module = typeof moduleLoader === 'function' ? await moduleLoader() : await moduleLoader;
        return { default: module[panel.export || 'default'] || module.default };
      } catch (error) {
        console.error('[Site-Hub Debug] Failed to load component:', panel.componentCode, 'from', contextKey, error);
        return { default: () => null };
      }
    });
  };

  const getRuntimeCodes = () => {
    return runtimes.map(r => r.id);
  };

  const loadRuntimes = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/runtime-environments');
      if (response.ok) {
        const data = await response.json();
        console.log('[Site-Hub Debug] Runtimes loaded:', data);
        const runtimesList = data.runtimes || [];
        console.log('[Site-Hub Debug] Runtimes list:', runtimesList);
        const siteHubRuntime = runtimesList.find((r: RuntimeEnvironment) => r.id === 'site-hub');
        console.log('[Site-Hub Debug] Site-Hub runtime found:', siteHubRuntime);
        setRuntimes(runtimesList);
      } else {
        // Fallback to default (Local-Core only)
        const defaultRuntimes: RuntimeEnvironment[] = [
          {
            id: 'local-core',
            name: 'Local-Core Runtime',
            description: 'Local execution environment, enabled by default',
            icon: '🖥',
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
      return { status: 'connected' as const, label: t('default' as any) || 'Default', icon: '✓' };
    }
    // Show OAuth auth_status badge when available
    if (runtime.auth_type === 'oauth2' && runtime.auth_status) {
      switch (runtime.auth_status) {
        case 'connected':
          return {
            status: 'connected' as const,
            label: runtime.auth_identity ? `Connected as ${runtime.auth_identity}` : 'Connected',
            icon: '✓',
          };
        case 'pending':
          return { status: 'not_configured' as const, label: 'Connecting...', icon: '⌛' };
        case 'error':
          return { status: 'inactive' as const, label: 'Auth Error', icon: '✗' };
        case 'disconnected':
          return { status: 'not_configured' as const, label: 'Not Connected', icon: '⚠' };
      }
    }
    switch (runtime.status) {
      case 'active':
        return { status: 'connected' as const, label: t('enabled' as any) || 'Enabled', icon: '✓' };
      case 'configured':
        return { status: 'connected' as const, label: t('configured' as any) || 'Configured', icon: '⚙' };
      case 'not_configured':
        return { status: 'not_configured' as const, label: t('notConfigured' as any) || 'Not Configured', icon: '⚠' };
      default:
        return { status: 'inactive' as const, label: t('disabled' as any) || 'Disabled', icon: '✗' };
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
              <div key={runtime.id} className="relative">
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
                />
                {/* OAuth Connect / Disconnect buttons */}
                {!runtime.isDefault && runtime.auth_type === 'oauth2' && (
                  <div className="mt-2 flex gap-2 px-1">
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
        const isSiteHub = selectedRuntime === 'site-hub' || runtime?.config_url?.includes('anafter.co');
        return (
          <BaseModal
            isOpen={true}
            onClose={() => setSelectedRuntime(null)}
            title={runtime?.name || t('runtimeConfiguration' as any) || 'Runtime Configuration'}
            maxWidth="max-w-2xl"
          >
            {isSiteHub ? (
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

      {/* Dynamic Settings Panels (Capability Slot) */}
      {settingsPanels.map((panel) => {
        console.log('[Site-Hub Debug] Processing panel:', panel.componentCode, panel);
        // Check showWhen conditions
        if (panel.showWhen?.runtimeCodes) {
          const runtimeCodes = getRuntimeCodes();
          console.log('[Site-Hub Debug] Panel requires runtime codes:', panel.showWhen.runtimeCodes);
          console.log('[Site-Hub Debug] Available runtime codes:', runtimeCodes);
          const hasRequiredRuntime = panel.showWhen.runtimeCodes.some(
            code => runtimeCodes.includes(code)
          );
          console.log('[Site-Hub Debug] Has required runtime:', hasRequiredRuntime, 'for panel', panel.componentCode);
          if (!hasRequiredRuntime) {
            console.log('[Site-Hub Debug] Panel', panel.componentCode, 'will not be rendered (missing required runtime)');
            return null;
          }
        }

        const ExtensionComponent = loadExtensionComponent(panel);
        const props = { ...panel.propsSchema };

        // Add workspaceId if required
        if (panel.requiresWorkspaceId) {
          const workspaceId = typeof window !== 'undefined'
            ? window.location.pathname.match(/\/workspaces\/([^\/]+)/)?.[1]
            : null;
          console.log('[Site-Hub Debug] Panel requires workspaceId:', workspaceId, 'for panel', panel.componentCode);
          if (workspaceId) {
            props.workspaceId = workspaceId;
          } else {
            console.warn('[Site-Hub Debug] Panel', panel.componentCode, 'requires workspaceId but not found in URL');
          }
        }

        console.log('[Site-Hub Debug] Rendering panel:', panel.componentCode, 'with props:', props);

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
            const ExtensionComponent = loadExtensionComponent(panel);
            const props = { ...panel.propsSchema };

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

/** Inline settings form for Site-Hub runtime (replaces iframe ExternalSettingsEmbed) */
function SiteHubSettingsForm({
  runtime,
  onSave,
  onCancel,
}: {
  runtime: RuntimeEnvironment;
  onSave: () => void;
  onCancel: () => void;
}) {
  const meta = runtime.metadata || {};
  const [configUrl, setConfigUrl] = useState(runtime.config_url || '');
  const [siteKey, setSiteKey] = useState(meta.site_key || '');
  const [chainagentId, setChainagentId] = useState(meta.chainagent_id || '');
  const [authToken, setAuthToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const apiUrl = getApiBaseUrl();
      const body: Record<string, any> = {
        config_url: configUrl || undefined,
        metadata: {
          site_key: siteKey || undefined,
          chainagent_id: chainagentId || undefined,
        },
      };

      // Update auth if token provided
      if (authToken) {
        body.auth_type = 'api_key';
        body.auth_config = { api_key: authToken };
      }

      const res = await fetch(
        `${apiUrl}/api/v1/runtime-environments/${runtime.id}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Save failed (${res.status}): ${detail}`);
      }

      onSave();
    } catch (e: any) {
      setError(e.message || 'Unknown error');
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full rounded-lg border border-gray-300 dark:border-gray-600 ' +
    'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ' +
    'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';

  const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

  return (
    <div className="space-y-5 p-2">
      {/* Config URL */}
      <div>
        <label className={labelClass}>Config URL</label>
        <input
          type="url"
          className={inputClass}
          value={configUrl}
          onChange={e => setConfigUrl(e.target.value)}
          placeholder="https://agent.anafter.co"
        />
        <p className="mt-1 text-xs text-gray-400">
          Site-Hub registry API base URL
        </p>
      </div>

      {/* Site Key */}
      <div>
        <label className={labelClass}>Site Key</label>
        <input
          type="text"
          className={inputClass}
          value={siteKey}
          onChange={e => setSiteKey(e.target.value)}
          placeholder="openseo-basic-anafter-co-an-after-ux-..."
        />
        <p className="mt-1 text-xs text-gray-400">
          From Site-Hub Console → Channel settings
        </p>
      </div>

      {/* ChainAgent ID */}
      <div>
        <label className={labelClass}>ChainAgent ID</label>
        <input
          type="text"
          className={inputClass}
          value={chainagentId}
          onChange={e => setChainagentId(e.target.value)}
          placeholder="UUID of the ChainAgent"
        />
        <p className="mt-1 text-xs text-gray-400">
          Required for fetching channels — find in Site-Hub Console
        </p>
      </div>

      {/* Auth Token */}
      <div>
        <label className={labelClass}>Auth Token (optional)</label>
        <input
          type="password"
          className={inputClass}
          value={authToken}
          onChange={e => setAuthToken(e.target.value)}
          placeholder="Leave empty to keep current token"
        />
        <p className="mt-1 text-xs text-gray-400">
          API key or bearer token for Site-Hub authentication
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          {t('cancel' as any) || 'Cancel'}
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : t('save' as any) || 'Save'}
        </button>
      </div>
    </div>
  );
}
