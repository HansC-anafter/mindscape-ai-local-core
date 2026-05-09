import { renderCapabilityUiHostPage } from '@/app/workspaces/[workspaceId]/capability-ui-hosts/renderCapabilityUiHostPage';
import IgCapabilityUiHost from './IgCapabilityUiHost';

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
    capabilityCode: 'ig',
    HostComponent: IgCapabilityUiHost,
  });
}
