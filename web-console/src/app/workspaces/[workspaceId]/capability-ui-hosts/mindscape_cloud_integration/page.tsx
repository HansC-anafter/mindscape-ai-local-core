import MindscapeCloudIntegrationCapabilityUiHost from './MindscapeCloudIntegrationCapabilityUiHost';
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
    capabilityCode: 'mindscape_cloud_integration',
    HostComponent: MindscapeCloudIntegrationCapabilityUiHost,
  });
}
