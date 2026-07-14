import type React from 'react';

import { getApiBaseUrl } from '../../../../../lib/api-url';
import { createLazySettingsExtensionComponent } from '../../../../../lib/settings-extension-component-loader';
import type { RuntimeSettingsExtensionProps, SettingsPanel } from './types';

function EmptyRuntimeSettingsExtension() {
  return null;
}

export function createRuntimeSettingsExtensionComponent(
  panel: SettingsPanel
): React.ComponentType<RuntimeSettingsExtensionProps> {
  if (!panel.capabilityCode || !panel.componentCode || !panel.importPath) {
    return EmptyRuntimeSettingsExtension;
  }

  return createLazySettingsExtensionComponent(
    {
      capability_code: panel.capabilityCode,
      component_code: panel.componentCode,
      description: panel.description,
      export: panel.export || 'default',
      import_path: panel.importPath,
      path: panel.path,
      asset_url: panel.assetUrl,
      integrity: panel.integrity,
      runtime: panel.runtime,
      legacy_context: panel.legacyContext,
      bytes: panel.bytes,
      asset_path: panel.assetPath,
    },
    getApiBaseUrl(),
  ) as React.ComponentType<RuntimeSettingsExtensionProps>;
}
