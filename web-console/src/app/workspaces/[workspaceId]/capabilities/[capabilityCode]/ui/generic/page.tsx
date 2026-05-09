import CapabilityUiGenericBootstrap from './CapabilityUiGenericBootstrap';

interface CapabilityUiGenericPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
}

export default function CapabilityUiGenericPage({ params }: CapabilityUiGenericPageProps) {
  return (
    <CapabilityUiGenericBootstrap
      workspaceId={params.workspaceId}
      capabilityCode={params.capabilityCode}
    />
  );
}
