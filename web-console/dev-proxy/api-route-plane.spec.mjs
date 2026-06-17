import { describe, expect, it } from 'vitest';

import { resolveApiRoutePlane } from './api-route-plane.mjs';

describe('API route plane', () => {
  it('routes install and admin operations to the control plane', () => {
    expect(resolveApiRoutePlane('/api/v1/capability-packs/install-from-file')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/capability-packs/installed-capabilities')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/capability-packs/installed-capabilities/ig/ui-components')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/capability-packs/install-jobs/job-1')).toMatchObject({
      plane: 'control',
    });
    expect(resolveApiRoutePlane('/api/v1/admin/capability-runtime/activate')).toMatchObject({
      plane: 'control',
    });
    expect(resolveApiRoutePlane('/api/v1/cloud-providers/default/install-default')).toMatchObject({
      plane: 'control',
    });
  });

  it('routes normal workspace and playbook APIs to the execution plane', () => {
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/summary')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
    });
    expect(resolveApiRoutePlane('/api/v1/playbooks/execute/run-1/status')).toMatchObject({
      plane: 'execution',
    });
    expect(resolveApiRoutePlane('/api/v1/ig/workbench/sidebar-summary')).toMatchObject({
      plane: 'execution',
    });
  });

  it('keeps host-runtime session gateway APIs on the execution plane', () => {
    expect(resolveApiRoutePlane('/api/v1/host-runtime/status')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
      reason: 'host_runtime_session_gateway',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/host-runtime/sessions')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
      reason: 'host_runtime_session_gateway',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/turns')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
      reason: 'host_runtime_session_gateway',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/stream')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
      reason: 'host_runtime_session_gateway',
    });
  });

  it('keeps workspace device-binding state on the control plane', () => {
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/pairing-codes')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/session-1/media-sessions/session-1/signal')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
  });

  it('keeps media traffic on the media proxy lane', () => {
    expect(resolveApiRoutePlane('/api/v1/media/assets/demo.png')).toMatchObject({
      plane: 'media',
      serviceId: 'local_core.media_proxy',
    });
  });
});
