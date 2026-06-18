import CapabilityUiHostStandaloneClient from '../../../CapabilityUiHostStandaloneClient';

interface CapabilityUiHostRuntimePageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: string[];
  };
}

export default function CapabilityUiHostRuntimePage({
  params,
}: CapabilityUiHostRuntimePageProps) {
  return (
    <CapabilityUiHostStandaloneClient
      workspaceId={params.workspaceId}
      capabilityCode={params.capabilityCode}
      surfacePath={params.surfacePath || []}
    />
  );
}
