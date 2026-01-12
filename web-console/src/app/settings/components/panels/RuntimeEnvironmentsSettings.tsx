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
// Use require.context to load capability components (webpack feature)
// @ts-ignore - require.context is a webpack feature, not standard TypeScript
// Use 'sync' mode instead of 'lazy' to avoid webpack pp/src path bug
const rawCapabilityComponentsContext = require.context('../../../capabilities', true, /\.tsx$/, 'sync');
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
  config_url?: string;
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

  useEffect(() => {
    loadRuntimes();
    loadSettingsPanels();
  }, []);

  const loadSettingsPanels = async () => {
    try {
      const apiUrl = await getApiUrl();
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
      return { status: 'active' as const, label: t('default') || 'Default', icon: '✓' };
    }
    switch (runtime.status) {
      case 'active':
        return { status: 'connected' as const, label: t('enabled') || 'Enabled', icon: '✓' };
      case 'configured':
        return { status: 'connected' as const, label: t('configured') || 'Configured', icon: '⚙' };
      case 'not_configured':
        return { status: 'not_connected' as const, label: t('notConfigured') || 'Not Configured', icon: '⚠' };
      default:
        return { status: 'not_connected' as const, label: t('disabled') || 'Disabled', icon: '✗' };
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
        title={t('runtimeEnvironments') || 'Runtime Environments'}
        description={t('runtimeEnvironmentsDescription') || 'Configure execution environments for running playbooks and processing tasks'}
      >
        <ToolGrid>
          {runtimes.map((runtime) => {
            const statusInfo = getStatusInfo(runtime);
            return (
              <ToolCard
                key={runtime.id}
                toolType={runtime.id}
                name={runtime.name}
                description={runtime.description}
                icon={runtime.icon}
                status={statusInfo}
                onConfigure={
                  runtime.isDefault
                    ? undefined
                    : () => setSelectedRuntime(runtime.id)
                }
              />
            );
          })}

          {/* Add Runtime button */}
          <ToolCard
            toolType="add-runtime"
            name={t('addRuntime') || 'Add Runtime Environment'}
            description={t('addRuntimeDescription') || 'Add a custom runtime execution environment'}
            icon="+"
            status={{ status: 'not_connected', label: t('add') || 'Add', icon: '+' }}
            onConfigure={() => setShowAddRuntimeModal(true)}
          />
        </ToolGrid>
      </Section>

      {/* Runtime Configuration Modal */}
      {selectedRuntime && (
        <BaseModal
          isOpen={true}
          onClose={() => setSelectedRuntime(null)}
          title={runtimes.find(r => r.id === selectedRuntime)?.name || t('runtimeConfiguration') || 'Runtime Configuration'}
          maxWidth="max-w-4xl"
        >
          <ExternalSettingsEmbed
            title={runtimes.find(r => r.id === selectedRuntime)?.name || t('runtimeConfiguration') || 'Runtime Configuration'}
            description={runtimes.find(r => r.id === selectedRuntime)?.description || ''}
            embedPath={getRuntimeConfigPath(selectedRuntime)}
            height="700px"
            onMessage={(event) => {
              if (event.data.type === 'RUNTIME_CONFIG_UPDATED') {
                setSelectedRuntime(null);
                loadRuntimes();
                showNotification('success', t('runtimeConfigurationUpdated') || 'Runtime configuration updated');
              }
            }}
          />
        </BaseModal>
      )}

      {/* Add Runtime Modal */}
      {showAddRuntimeModal && (
        <AddRuntimeModal
          isOpen={true}
          onClose={() => setShowAddRuntimeModal(false)}
          onSuccess={(newRuntime) => {
            setRuntimes([...runtimes, newRuntime]);
            setShowAddRuntimeModal(false);
            showNotification('success', t('runtimeAddedSuccessfully', { name: newRuntime.name }) || `Runtime "${newRuntime.name}" added successfully`);
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
                {t('loading') || 'Loading'} {panel.title}...
              </div>
            }>
              <ExtensionComponent {...props} />
            </Suspense>
          </Section>
        );
      })}

    </div>
  );
}
