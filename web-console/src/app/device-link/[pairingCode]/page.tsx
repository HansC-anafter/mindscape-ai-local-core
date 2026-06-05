import DeviceLinkPageClient from './DeviceLinkPageClient';

export default function DeviceLinkPage({
  params,
  searchParams,
}: {
  params: { pairingCode?: string };
  searchParams?: { workspaceId?: string; sourceMode?: string };
}) {
  return (
    <DeviceLinkPageClient
      pairingCode={params.pairingCode || ''}
      workspaceId={searchParams?.workspaceId || 'default'}
      initialSourceMode={searchParams?.sourceMode === 'camera' ? 'camera' : 'phone'}
    />
  );
}
