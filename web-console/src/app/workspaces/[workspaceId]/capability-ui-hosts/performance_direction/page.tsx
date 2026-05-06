import PerformanceDirectionCapabilityUiHost from './PerformanceDirectionCapabilityUiHost';
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
    capabilityCode: 'performance_direction',
    HostComponent: PerformanceDirectionCapabilityUiHost,
  });
}
