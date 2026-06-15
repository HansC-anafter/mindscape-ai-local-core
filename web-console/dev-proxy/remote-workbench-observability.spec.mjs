import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { createRemoteWorkbenchObservability } from './remote-workbench-observability.mjs';

const tempDirs = [];

function makeTempDir() {
  const nextDir = fs.mkdtempSync(path.join(os.tmpdir(), 'remote-workbench-observability-'));
  tempDirs.push(nextDir);
  return nextDir;
}

function createGatewayConfig() {
  return {
    publicOrigin: 'https://remote-workbench.mindscapeai.app',
  };
}

afterEach(() => {
  while (tempDirs.length > 0) {
    const target = tempDirs.pop();
    fs.rmSync(target, { recursive: true, force: true });
  }
});

describe('remote workbench observability', () => {
  it('builds public-host summary and audit tails without writing to the database plane', async () => {
    const observability = createRemoteWorkbenchObservability({
      dataDir: makeTempDir(),
      loadRunnerSnapshot: async () => ({
        status: 'ok',
        runners: [{
          runner_id: 'browser-1',
          runner_type: 'browser_local',
          inflight: 2,
          max_inflight: 3,
          admission: {
            state: 'soft_defer',
            reasons: ['browser_session_slots'],
          },
        }],
      }),
    });

    const proxyObservation = observability.createObservation({
      requestId: 1,
      requestUrl: '/workspaces/ws-1/capability-ui-hosts/yogacoach?component=YogaPracticeWorkbenchPage',
      requestMethod: 'GET',
      requestHeaders: {
        host: 'remote-workbench.mindscapeai.app',
      },
      requestResult: {
        context: {
          path: '/workspaces/ws-1/capability-ui-hosts/yogacoach',
          workspaceId: 'ws-1',
          capabilityCode: 'yogacoach',
        },
      },
      mobileWorkbenchGatewayConfig: createGatewayConfig(),
    });
    await observability.recordCompletedRequest(proxyObservation, {
      event: 'finish',
      statusCode: 200,
      responseBytes: 4096,
      durationMs: 120,
      upstreamKind: 'next_dev',
      upstreamStatus: 200,
      upstreamHeaderMs: 25,
    });

    const deniedObservation = observability.createObservation({
      requestId: 2,
      requestUrl: '/api/v1/capabilities/yogacoach/practice-sessions?workspace_id=ws-1',
      requestMethod: 'GET',
      requestHeaders: {
        host: 'remote-workbench.mindscapeai.app',
      },
      requestResult: {
        context: {
          path: '/api/v1/capabilities/yogacoach/practice-sessions',
          workspaceId: 'ws-1',
          capabilityCode: 'yogacoach',
        },
        reason_code: 'capability_not_allowed',
      },
      mobileWorkbenchGatewayConfig: createGatewayConfig(),
    });
    await observability.recordDeniedRequest(deniedObservation, {
      requestResult: {
        reason_code: 'capability_not_allowed',
      },
      statusCode: 403,
      responseBytes: 128,
    });

    const loopbackObservation = observability.createObservation({
      requestId: 3,
      requestUrl: '/api/v1/workspaces/ws-1/tasks?include_completed=true',
      requestMethod: 'GET',
      requestHeaders: {
        host: 'localhost:8300',
      },
      requestResult: {
        context: {
          path: '/api/v1/workspaces/ws-1/tasks',
          workspaceId: 'ws-1',
          capabilityCode: 'yogacoach',
        },
        ingress: 'local_control_plane',
      },
      mobileWorkbenchGatewayConfig: createGatewayConfig(),
    });
    await observability.recordCompletedRequest(loopbackObservation, {
      event: 'finish',
      statusCode: 200,
      responseBytes: 512,
      durationMs: 40,
      upstreamKind: 'backend_execution_api',
      upstreamStatus: 200,
      upstreamHeaderMs: 12,
    });

    const summary = await observability.readSummary({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });
    const audit = await observability.readAuditTail({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
      limit: 10,
    });

    expect(summary.request_totals).toMatchObject({
      total: 2,
      proxied: 1,
      denied: 1,
      errors: 0,
      response_bytes: 4224,
    });
    expect(summary.by_route_class).toEqual(expect.arrayContaining([
      expect.objectContaining({
        route_class: 'host_page',
        requests: 1,
      }),
      expect.objectContaining({
        route_class: 'capability_api',
        requests: 1,
        denied: 1,
      }),
    ]));
    expect(summary.runner_snapshot).toMatchObject({
      browser_runners: 1,
      inflight_total: 2,
      max_inflight_total: 3,
      soft_defer_count: 1,
      soft_defer_reasons: ['browser_session_slots'],
    });
    expect(audit.events).toHaveLength(2);
    expect(audit.events.map((event) => event.origin_type)).toEqual(['public_host', 'public_host']);
    expect(new Set(audit.events.map((event) => event.outcome))).toEqual(new Set(['proxied', 'denied']));
  });
});
