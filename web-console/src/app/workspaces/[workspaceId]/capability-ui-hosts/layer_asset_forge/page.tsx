import LayerAssetForgeCapabilityUiHost from './LayerAssetForgeCapabilityUiHost';
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
    capabilityCode: 'layer_asset_forge',
    HostComponent: LayerAssetForgeCapabilityUiHost,
  });
}
