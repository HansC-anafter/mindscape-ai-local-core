import { headers } from 'next/headers';

import { renderCapabilityUiHostPage } from '../../renderCapabilityUiHostPage';

interface CapabilityUiHostPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: string[];
  };
}

export default function CapabilityUiHostPage({
  params,
}: CapabilityUiHostPageProps) {
  return renderCapabilityUiHostPage({
    workspaceId: params.workspaceId,
    capabilityCode: params.capabilityCode,
    surfacePath: params.surfacePath || [],
    remoteSurfaceMode: headers().get('x-mindscape-remote-ingress') === 'remote_workbench',
  });
}
