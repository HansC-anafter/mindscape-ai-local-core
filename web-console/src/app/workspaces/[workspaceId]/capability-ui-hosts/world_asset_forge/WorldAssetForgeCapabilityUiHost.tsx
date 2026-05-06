'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as WorldAssetForgePageModule0 from '@/app/capabilities/world_asset_forge/components/WorldAssetForgePage';

const componentModules: Record<string, Record<string, unknown>> = {
  "WorldAssetForgePage": WorldAssetForgePageModule0 as Record<string, unknown>,
};

export default function WorldAssetForgeCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
