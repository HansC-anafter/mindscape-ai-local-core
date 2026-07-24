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

  it('routes settings descriptors and exact Remote Workbench policies to control', () => {
    for (const path of [
      '/api/v1/settings/extensions',
      '/api/v1/settings/extensions?section=remote-workbench-global-access',
      '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy',
      '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy/',
      '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces/ws-1/policy',
      '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces/ws-1/policy/',
    ]) {
      expect(resolveApiRoutePlane(path)).toMatchObject({
        plane: 'control',
        serviceId: 'local_core.control_api',
      });
    }
    expect(resolveApiRoutePlane(
      '/api/v1/capabilities/mindscape_cloud_integration/workspace-runtime-config/ws-1',
    )).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
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

  it('keeps the Remote bridge on control and device/media sessions on execution', () => {
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/agents/bridge-service')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/agents/bridge-service/start')).toMatchObject({
      plane: 'control',
      serviceId: 'local_core.control_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/pairing-codes')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
    });
    expect(resolveApiRoutePlane('/api/v1/workspaces/ws-1/device-bindings/session-1/media-sessions/session-1/signal')).toMatchObject({
      plane: 'execution',
      serviceId: 'local_core.execution_api',
    });
  });

  it('keeps media traffic on the media proxy lane', () => {
    expect(resolveApiRoutePlane('/api/v1/media/assets/demo.png')).toMatchObject({
      plane: 'media',
      serviceId: 'local_core.media_proxy',
    });
  });
});
