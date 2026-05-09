import { lazy, type ComponentType } from 'react';

export interface SettingsExtensionComponentDescriptor {
  capability_code: string;
  component_code: string;
  export?: string;
  import_path: string;
}

type SettingsExtensionModule = Record<string, any>;
type SettingsExtensionLoader = () => Promise<SettingsExtensionModule>;

const settingsExtensionLoaders: Record<string, SettingsExtensionLoader> = {
  'comfyui_runtime:ComfyUIRuntimePanel': () => import('@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimePanel'),
  'comfyui_runtime:ComfyUIRuntimeSettingsPanel': () => import('@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimeSettingsPanel'),
  'mindscape_cloud_integration:MindscapeCloudChannelBindingPanel': () => import('@/app/capabilities/mindscape_cloud_integration/components/MindscapeCloudChannelBindingPanel'),
  'web_generation:WordPressSitesPanel': () => import('@/app/capabilities/web_generation/components/WordPressSitesPanel'),
};

function EmptySettingsExtension() {
  return null;
}

function loaderKey(panel: SettingsExtensionComponentDescriptor): string {
  return `${panel.capability_code}:${panel.component_code}`;
}

export function createLazySettingsExtensionComponent(
  panel: SettingsExtensionComponentDescriptor
): ComponentType<any> {
  return lazy(async () => {
    try {
      const loader = settingsExtensionLoaders[loaderKey(panel)];
      if (!loader) {
        console.warn('[settings-extension-loader] Settings extension component not registered:', {
          capability_code: panel.capability_code,
          component_code: panel.component_code,
          import_path: panel.import_path,
        });
        return { default: EmptySettingsExtension };
      }

      const module = await loader();
      const Component = module[panel.export || 'default'] || module.default;
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
