import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { createRemoteWorkbenchObservability } from './remote-workbench-observability.mjs';
import { createRemoteWorkbenchLogStore } from './remote-workbench-observability/storage.mjs';

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

function createStore(baseDir) {
  return createRemoteWorkbenchLogStore({
    baseDir,
    activeLogPath: path.join(baseDir, 'access.current.ndjson'),
  });
}

async function expectUnsafeStorage(store) {
  await expect(store.readRawRecords()).rejects.toMatchObject({
    code: 'REMOTE_WORKBENCH_AUDIT_STORAGE_UNSAFE',
  });
}

afterEach(() => {
  vi.restoreAllMocks();
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

  it('fails closed when the audit base directory is a symlink', async () => {
    const root = makeTempDir();
    const realBase = path.join(root, 'real-audit');
    const linkedBase = path.join(root, 'linked-audit');
    fs.mkdirSync(realBase, { mode: 0o700 });
    fs.symlinkSync(realBase, linkedBase, 'dir');

    await expectUnsafeStorage(createStore(linkedBase));
  });

  it.each([
    ['non-directory', (baseDir) => fs.writeFileSync(baseDir, 'not-a-directory')],
    ['wrong-mode directory', (baseDir) => {
      fs.mkdirSync(baseDir, { mode: 0o700 });
      fs.chmodSync(baseDir, 0o755);
    }],
  ])('fails closed when the audit base is a %s', async (_label, prepare) => {
    const baseDir = path.join(makeTempDir(), 'audit');
    prepare(baseDir);

    await expectUnsafeStorage(createStore(baseDir));
  });

  it('does not follow an active audit symlink for append or read', async () => {
    const root = makeTempDir();
    const baseDir = path.join(root, 'audit');
    const external = path.join(root, 'external.ndjson');
    fs.mkdirSync(baseDir, { mode: 0o700 });
    fs.writeFileSync(external, 'sentinel\n', { mode: 0o600 });
    fs.symlinkSync(external, path.join(baseDir, 'access.current.ndjson'));
    const store = createStore(baseDir);
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    await store.enqueueAppend({ should_not_escape: true });

    expect(error).toHaveBeenCalledTimes(1);
    expect(fs.readFileSync(external, 'utf8')).toBe('sentinel\n');
    await expectUnsafeStorage(store);
    error.mockRestore();
  });

  it('fails closed when an archive path is a symlink', async () => {
    const root = makeTempDir();
    const baseDir = path.join(root, 'audit');
    const external = path.join(root, 'external.ndjson');
    fs.mkdirSync(baseDir, { mode: 0o700 });
    fs.writeFileSync(external, '{"outside":true}\n', { mode: 0o600 });
    fs.symlinkSync(external, path.join(baseDir, 'access.1.ndjson'));

    await expectUnsafeStorage(createStore(baseDir));
  });

  it.each(['access.current.ndjson', 'access.1.ndjson'])(
    'fails closed when %s is non-regular',
    async (filename) => {
      const baseDir = path.join(makeTempDir(), 'audit');
      fs.mkdirSync(baseDir, { mode: 0o700 });
      fs.mkdirSync(path.join(baseDir, filename), { mode: 0o700 });

      await expectUnsafeStorage(createStore(baseDir));
    },
  );
});
