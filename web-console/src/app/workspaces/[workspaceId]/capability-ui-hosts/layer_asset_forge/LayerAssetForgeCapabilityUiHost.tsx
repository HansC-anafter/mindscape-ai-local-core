'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as DerivationGraphViewerModule0 from '@/app/capabilities/layer_asset_forge/components/DerivationGraphViewer';
import * as ElementAssetCardModule1 from '@/app/capabilities/layer_asset_forge/components/ElementAssetCard';
import * as LayerAssetForgePageModule2 from '@/app/capabilities/layer_asset_forge/components/LayerAssetForgePage';
import * as LayerPreviewPanelModule3 from '@/app/capabilities/layer_asset_forge/components/LayerPreviewPanel';

const componentModules: Record<string, Record<string, unknown>> = {
  "DerivationGraphViewer": DerivationGraphViewerModule0 as Record<string, unknown>,
  "ElementAssetCard": ElementAssetCardModule1 as Record<string, unknown>,
  "LayerAssetForgePage": LayerAssetForgePageModule2 as Record<string, unknown>,
  "LayerPreviewPanel": LayerPreviewPanelModule3 as Record<string, unknown>,
};

export default function LayerAssetForgeCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
