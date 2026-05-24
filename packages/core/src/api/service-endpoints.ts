export type EndpointAudience =
  | 'browser_public'
  | 'host_public'
  | 'container_internal'
  | 'server_internal';

export interface ServiceEndpoint {
  service_id: string;
  audience: EndpointAudience;
  url: string;
  source?: string;
  label?: string;
  description?: string;
  is_user_editable?: boolean;
}

export interface ServiceEndpointSnapshot {
  version: number;
  endpoints: ServiceEndpoint[];
}

let cachedSnapshot: ServiceEndpointSnapshot | null = null;

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

function loadSeedSnapshot(): ServiceEndpointSnapshot {
  if (cachedSnapshot) {
    return cachedSnapshot;
  }

  const payload = serviceEndpointSeed as ServiceEndpointSnapshot;
  cachedSnapshot = {
    version: Number(payload.version || 1),
    endpoints: Array.isArray(payload.endpoints) ? payload.endpoints : [],
  };
  return cachedSnapshot;
}

export function clearServiceEndpointSnapshotCache(): void {
  cachedSnapshot = null;
}

export function getServiceEndpointSnapshot(): ServiceEndpointSnapshot {
  return loadSeedSnapshot();
}

export function getServiceEndpointUrl(
  serviceId: string,
  audience: EndpointAudience
): string {
  if (isBrowser() && audience === 'browser_public' && serviceId.startsWith('local_core.')) {
    return '';
  }

  const endpoint = getServiceEndpointSnapshot().endpoints.find(
    candidate => candidate.service_id === serviceId && candidate.audience === audience
  );
  return endpoint?.url || '';
}
import serviceEndpointSeed from '../../../../config/service-endpoints.seed.json';
