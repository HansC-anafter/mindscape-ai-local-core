'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ComfyUIRuntimePanelModule0 from '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimePanel';
import * as ComfyUIRuntimeSettingsPanelModule1 from '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimeSettingsPanel';

const componentModules: Record<string, Record<string, unknown>> = {
  "ComfyUIRuntimePanel": ComfyUIRuntimePanelModule0 as Record<string, unknown>,
  "ComfyUIRuntimeSettingsPanel": ComfyUIRuntimeSettingsPanelModule1 as Record<string, unknown>,
};

export default function ComfyuiRuntimeCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
