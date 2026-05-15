import { lazy, type ComponentType } from 'react';

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
}

function EmptySettingsExtension() {
  return null;
}

export function createLazySettingsExtensionComponent(
  panel: SettingsExtensionComponentDescriptor,
  apiUrl: string,
): ComponentType<any> {
  return lazy(async () => {
    try {
      primeCapabilityUIComponentMetadata(panel.capability_code, [
        {
          code: panel.component_code,
          path: inferComponentPathFromImportPath(panel),
          description: panel.description || '',
          export: panel.export || 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: panel.import_path,
        },
      ]);

      const Component = await loadCapabilityUIComponent(
        panel.capability_code,
        panel.component_code,
        apiUrl,
      );
      return { default: Component || EmptySettingsExtension };
    } catch (error) {
      console.error('[settings-extension-loader] Failed to load settings extension component:', {
        capability_code: panel.capability_code,
        component_code: panel.component_code,
        error,
      });
      return { default: EmptySettingsExtension };
    }
  });
}
