'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as BlenderBridge3DMeshRuntimeSettingsPanelModule0 from '@/app/capabilities/blender_bridge/components/BlenderBridge3DMeshRuntimeSettingsPanel';
import * as BlenderBridgeWorkbenchPageModule1 from '@/app/capabilities/blender_bridge/components/BlenderBridgeWorkbenchPage';

const componentModules: Record<string, Record<string, unknown>> = {
  "BlenderBridge3DMeshRuntimeSettingsPanel": BlenderBridge3DMeshRuntimeSettingsPanelModule0 as Record<string, unknown>,
  "BlenderBridgeWorkbenchPage": BlenderBridgeWorkbenchPageModule1 as Record<string, unknown>,
};

export default function BlenderBridgeCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
