import { buildDeviceControlWebSocketUrl } from '@/lib/device-binding/deviceBindingClient';

export function buildExternalProviderBridgePayload({
  apiBase,
  pairingCode,
  workspaceId,
}: {
  apiBase: string;
  pairingCode: string;
  workspaceId: string;
}): string {
  return JSON.stringify({
    transport: 'device_binding_control_ws',
    api_base: apiBase,
    workspace_id: workspaceId,
    pairing_code: pairingCode,
    control_ws_url: buildDeviceControlWebSocketUrl({ apiBase, workspaceId, pairingCode }),
    source_join: {
      type: 'source_join',
      display_name: 'External provider bridge',
      source_types: ['external_provider_camera'],
      metadata: {
        capture_surface: 'external_provider_bridge',
      },
    },
  }, null, 2);
}
