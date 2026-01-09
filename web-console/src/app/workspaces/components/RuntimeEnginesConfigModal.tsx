'use client';

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { getApiUrl } from '../../../lib/api-url';
import { BaseModal } from '@/components/BaseModal';

// Use require.context to load capability components (webpack feature)
// @ts-ignore - require.context is a webpack feature, not standard TypeScript
// eslint-disable-next-line @typescript-eslint/no-var-requires
const capabilityComponentsContext = require.context('../../capabilities', true, /\.tsx$/, 'lazy');

interface SettingsPanel {
  capability_code: string;
  component_code: string;
  title: string;
  description?: string;
  requires_workspace_id?: boolean;
  show_when?: {
    runtime_codes?: string[];
  };
  props_schema?: Record<string, any>;
  import_path: string;
  export: string;
}

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
  metadata?: {
    created_by?: string;
    signature?: {
      type?: string;
      base_url?: string;
    };
    [key: string]: any;
  };
}

interface RuntimeEnginesConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
}

export default function RuntimeEnginesConfigModal({
  isOpen,
  onClose,
  workspaceId,
}: RuntimeEnginesConfigModalProps) {
  const [settingsPanels, setSettingsPanels] = useState<SettingsPanel[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      loadRuntimes();
      loadSettingsPanels();
    }
  }, [isOpen, workspaceId]);

  const loadSettingsPanels = async () => {
    try {
      setLoading(true);
      const apiUrl = await getApiUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/settings/extensions?section=runtime-environments`
      );
      if (response.ok) {
        const data = await response.json();
        setSettingsPanels(data);
      }
    } catch (error) {
      console.error('Failed to load settings panels:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadRuntimes = async () => {
    try {
      const response = await fetch('/api/v1/runtime-environments');
      if (response.ok) {
        const data = await response.json();
        setRuntimes(data.runtimes || []);
      }
    } catch (error) {
      console.error('Failed to load runtimes:', error);
    }
  };

  const loadExtensionComponent = (panel: SettingsPanel) => {
    // Convert @/app/capabilities/... to require.context key
    // @/app/capabilities/site_hub_integration/components/SiteHubChannelBindingPanel
    // -> ./site_hub_integration/components/SiteHubChannelBindingPanel.tsx
    const convertImportPathToContextKey = (importPath: string): string | null => {
      if (!importPath.startsWith('@/app/capabilities/')) {
        return null;
      }
      const relativePath = importPath.replace('@/app/capabilities/', './');
      return `${relativePath}.tsx`;
    };

    const contextKey = convertImportPathToContextKey(panel.import_path);

    if (!contextKey) {
      return lazy(() => Promise.resolve({
        default: () => (
          <div className="text-sm text-red-500 p-4">
            Invalid import path: {panel.import_path}
          </div>
        )
      }));
    }

    return lazy(async () => {
      try {
        // Use require.context to load the component (webpack handles this at build time)
        const moduleLoader = capabilityComponentsContext(contextKey);
        const module = typeof moduleLoader === 'function'
          ? await moduleLoader()
          : await moduleLoader;

        const component = module[panel.export || 'default'] || module.default;
        if (!component) {
          console.error(`Component ${panel.component_code} export "${panel.export || 'default'}" not found in module`);
          return {
            default: () => (
              <div className="text-sm text-red-500 p-4">
                Component export not found: {panel.export || 'default'}
              </div>
            )
          };
        }
        return { default: component };
      } catch (error) {
        console.error(`Failed to load component ${panel.component_code} from ${contextKey}:`, error);
        return {
          default: () => (
            <div className="text-sm text-red-500 p-4">
              Failed to load component: {panel.component_code}<br/>
              Context Key: {contextKey}<br/>
              Original: {panel.import_path}<br/>
              Error: {error instanceof Error ? error.message : String(error)}
            </div>
          )
        };
      }
    });
  };

  const getRuntimeCodes = () => {
    return runtimes.map(r => r.id);
  };

  const shouldShowPanel = (panel: SettingsPanel): boolean => {
    if (!panel.show_when?.runtime_codes) {
      return true;
    }

    const runtimeCodes = getRuntimeCodes();

    // First try exact match by runtime id
    let hasRequiredRuntime = panel.show_when.runtime_codes.some(
      code => runtimeCodes.includes(code)
    );

    // If no exact match, try dynamic matching by metadata.created_by
    if (!hasRequiredRuntime) {
      hasRequiredRuntime = runtimes.some((runtime) => {
        const metadata = runtime.metadata || {};
        const createdBy = metadata.created_by;
        return createdBy === panel.capability_code;
      });
    }

    // Always show panel (user can set it up even without runtime)
    return true;
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="執行引擎配置"
      maxWidth="max-w-4xl"
    >
      <div className="space-y-6">
        {loading ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            Loading runtime engines...
          </div>
        ) : settingsPanels.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No runtime engines configured. Install capability packs to add execution engines.
          </div>
        ) : (
          settingsPanels.map((panel) => {
            if (!shouldShowPanel(panel)) {
              return null;
            }

            const ExtensionComponent = loadExtensionComponent(panel);
            // Build props from props_schema, ensuring workspaceId is included
            const props: Record<string, any> = { workspaceId };
            if (panel.props_schema) {
              Object.keys(panel.props_schema).forEach(key => {
                // workspaceId is already set, skip if duplicate
                if (key !== 'workspaceId') {
                  const schemaValue = panel.props_schema?.[key];
                  if (schemaValue !== undefined) {
                    props[key] = schemaValue;
                  }
                }
              });
            }

            return (
              <div
                key={`${panel.capability_code}:${panel.component_code}`}
                className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4"
              >
                {/* Title and description are rendered by the component itself, no need to duplicate */}
                <Suspense fallback={
                  <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                    Loading {panel.title}...
                  </div>
                }>
                  <ExtensionComponent {...props} />
                </Suspense>
              </div>
            );
          })
        )}
      </div>
    </BaseModal>
  );
}

