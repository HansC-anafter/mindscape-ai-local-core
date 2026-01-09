'use client';

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { getApiUrl } from '../../../../lib/api-url';

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

export default function RuntimeEnginesPanel({
  workspaceId,
  panels
}: {
  workspaceId: string;
  panels?: any[];
}) {
  const [settingsPanels, setSettingsPanels] = useState<SettingsPanel[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRuntimes();
    loadSettingsPanels();
  }, [workspaceId]);

  const loadSettingsPanels = async () => {
    try {
      // Use provided panels if available, otherwise fetch
      if (panels && panels.length > 0) {
        setSettingsPanels(panels);
        setLoading(false);
        return;
      }
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
    const importPath = panel.import_path.replace('@/app/capabilities/', '../../../capabilities/');
    return lazy(() =>
      import(/* @vite-ignore */ importPath)
        .then(module => {
          return { default: module[panel.export || 'default'] };
        })
        .catch((error) => {
          // Only log errors in development, and suppress expected module not found errors
          if (process.env.NODE_ENV === 'development' && !error.message?.includes('Failed to fetch dynamically imported module')) {
            console.debug(`Failed to load component ${panel.component_code} from ${importPath}:`, error.message);
          }
          return { default: () => null };
        })
    );
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

  if (loading) {
    return (
      <div className="text-[10px] text-secondary dark:text-gray-400 py-1">
        Loading runtime engines...
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Dynamic Runtime Extension Components */}
      {settingsPanels.length === 0 ? (
        <div className="text-[10px] text-secondary dark:text-gray-400 italic">
          No runtime engines configured
        </div>
      ) : (
        settingsPanels.map((panel) => {
          if (!shouldShowPanel(panel)) {
            return null;
          }

          const ExtensionComponent = loadExtensionComponent(panel);
          const props = { ...panel.props_schema, workspaceId };

          return (
            <div key={`${panel.capability_code}:${panel.component_code}`} className="space-y-1">
              <Suspense fallback={
                <div className="text-[10px] text-secondary dark:text-gray-400 py-1">
                  Loading...
                </div>
              }>
                <ExtensionComponent {...props} />
              </Suspense>
            </div>
          );
        })
      )}
    </div>
  );
}

