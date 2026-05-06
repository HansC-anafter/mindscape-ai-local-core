import BrandIdentityCapabilityUiHost from './BrandIdentityCapabilityUiHost';
import { renderCapabilityUiHostPage } from '../renderCapabilityUiHostPage';

interface CapabilityUiHostPageProps {
  params: {
    workspaceId: string;
  };
}

export default async function CapabilityUiHostPage({
  params,
}: CapabilityUiHostPageProps) {
  return renderCapabilityUiHostPage({
    workspaceId: params.workspaceId,
    capabilityCode: 'brand_identity',
    HostComponent: BrandIdentityCapabilityUiHost,
  });
}
