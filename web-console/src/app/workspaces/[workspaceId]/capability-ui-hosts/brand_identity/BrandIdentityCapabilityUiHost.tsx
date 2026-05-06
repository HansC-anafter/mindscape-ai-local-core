'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as BrandFoundationCardsModule0 from '@/app/capabilities/brand_identity/components/BrandFoundationCards';
import * as CISMappingViewModule1 from '@/app/capabilities/brand_identity/components/CISMappingView';
import * as DecisionCardModule2 from '@/app/capabilities/brand_identity/components/DecisionCard';
import * as LensChronicleModule3 from '@/app/capabilities/brand_identity/components/LensChronicle';
import * as LensImpactDashboardModule4 from '@/app/capabilities/brand_identity/components/LensImpactDashboard';
import * as LensProfileCardModule5 from '@/app/capabilities/brand_identity/components/LensProfileCard';
import * as ResponsibilityFlowMapModule6 from '@/app/capabilities/brand_identity/components/ResponsibilityFlowMap';
import * as VersionCompareViewModule7 from '@/app/capabilities/brand_identity/components/VersionCompareView';

const componentModules: Record<string, Record<string, unknown>> = {
  "BrandFoundationCards": BrandFoundationCardsModule0 as Record<string, unknown>,
  "CISMappingView": CISMappingViewModule1 as Record<string, unknown>,
  "DecisionCard": DecisionCardModule2 as Record<string, unknown>,
  "LensChronicle": LensChronicleModule3 as Record<string, unknown>,
  "LensImpactDashboard": LensImpactDashboardModule4 as Record<string, unknown>,
  "LensProfileCard": LensProfileCardModule5 as Record<string, unknown>,
  "ResponsibilityFlowMap": ResponsibilityFlowMapModule6 as Record<string, unknown>,
  "VersionCompareView": VersionCompareViewModule7 as Record<string, unknown>,
};

export default function BrandIdentityCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
