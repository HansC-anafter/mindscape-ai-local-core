import { createElement, lazy, type ComponentType } from 'react';

import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from './capability-ui-loader';
import { inferComponentPathFromImportPath } from './workspace-right-region/workspace-right-region-contract';

export interface SettingsExtensionComponentDescriptor {
  capability_code: string;
  component_code: string;
  description?: string;
  export?: string;
  import_path: string;
  path?: string;
  asset_url?: string;
  integrity?: string;
  runtime?: string;
  legacy_context?: boolean;
  bytes?: number;
  asset_path?: string;
}

function createSettingsExtensionLoadFailure(
  capabilityCode: string,
  componentCode: string,
): ComponentType<any> {
  function SettingsExtensionLoadFailure() {
    return createElement(
      'div',
      { role: 'alert', className: 'p-3 text-sm text-red-700 dark:text-red-300' },
      `Unable to load settings extension ${capabilityCode}/${componentCode}.`,
    );
  }
  return SettingsExtensionLoadFailure;
}

export function createLazySettingsExtensionComponent(
  panel: SettingsExtensionComponentDescriptor,
  apiUrl: string,
  workspaceId?: string,
): ComponentType<any> {
  return lazy(async () => {
    try {
      if (panel.asset_url || panel.legacy_context === true || panel.runtime === 'legacy_context') {
        primeCapabilityUIComponentMetadata(panel.capability_code, [
          {
            code: panel.component_code,
            path: panel.path || inferComponentPathFromImportPath(panel),
            description: panel.description || '',
            export: panel.export || 'default',
            artifact_types: [],
            playbook_codes: [],
            import_path: panel.import_path,
            asset_url: panel.asset_url,
            integrity: panel.integrity,
            runtime: panel.runtime,
            legacy_context: panel.legacy_context,
            bytes: panel.bytes,
            asset_path: panel.asset_path,
          },
        ]);
      }

      const Component = await loadCapabilityUIComponent(
        panel.capability_code,
        panel.component_code,
        apiUrl,
        workspaceId,
      );
      return {
        default: Component || createSettingsExtensionLoadFailure(
          panel.capability_code,
          panel.component_code,
        ),
      };
    } catch (error) {
      console.error('[settings-extension-loader] Failed to load settings extension component:', {
        capability_code: panel.capability_code,
        component_code: panel.component_code,
        error,
      });
      return {
        default: createSettingsExtensionLoadFailure(
          panel.capability_code,
          panel.component_code,
        ),
      };
    }
  });
}
