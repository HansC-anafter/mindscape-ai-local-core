import { describe, expect, it } from 'vitest';

import {
  clearServiceEndpointSnapshotCache,
  getServiceEndpointSnapshot,
  getServiceEndpointUrl,
} from './service-endpoints';

describe('service endpoint resolver', () => {
  it('loads the shared seed file for server-side resolution', () => {
    clearServiceEndpointSnapshotCache();

    const snapshot = getServiceEndpointSnapshot();

    expect(snapshot.endpoints.some(endpoint => endpoint.service_id === 'local_core.media_proxy')).toBe(true);
    expect(getServiceEndpointUrl('local_core.control_api', 'server_internal')).toBe(
      'http://backend-control:8210'
    );
    expect(getServiceEndpointUrl('local_core.media_proxy', 'container_internal')).toBe(
      'http://media-proxy:8000'
    );
  });
});
