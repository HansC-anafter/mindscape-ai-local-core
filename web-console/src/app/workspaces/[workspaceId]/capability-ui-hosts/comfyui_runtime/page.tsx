import ComfyuiRuntimeCapabilityUiHost from './ComfyuiRuntimeCapabilityUiHost';
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
    capabilityCode: 'comfyui_runtime',
    HostComponent: ComfyuiRuntimeCapabilityUiHost,
  });
}
