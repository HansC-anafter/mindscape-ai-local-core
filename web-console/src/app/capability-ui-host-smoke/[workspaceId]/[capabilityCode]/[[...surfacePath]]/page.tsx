interface CapabilityUiHostSmokePageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: string[];
  };
}

export default function CapabilityUiHostSmokePage({
  params,
}: CapabilityUiHostSmokePageProps) {
  return (
    <main data-testid="capability-ui-host-smoke">
      <h1>Capability host smoke</h1>
      <p>workspaceId: {params.workspaceId}</p>
      <p>capabilityCode: {params.capabilityCode}</p>
      <p>surfacePath: {(params.surfacePath || []).join('/')}</p>
    </main>
  );
}
