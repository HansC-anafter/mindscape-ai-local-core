import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getEffectiveWorkspaceProductConfiguration,
  replaceWorkspaceProductConfiguration,
  WorkspaceProductApiError,
} from './workspace-product-configuration-api';

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

describe('workspace product configuration API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses one effective GET with explicit group context', async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => response({ snapshot_hash: 'a'.repeat(64) }));
    vi.stubGlobal('fetch', fetchMock);

    await getEffectiveWorkspaceProductConfiguration({
      workspaceId: 'ws one',
      activeGroupId: 'wg-one',
      topologyRevision: 7,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/api/v1/workspaces/ws%20one/product-configuration/effective'
      + '?active_group_id=wg-one&observed_topology_revision=7',
    );
  });

  it('applies one complete replacement and trusts the response snapshot', async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => response({ snapshot_hash: 'b'.repeat(64) }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await replaceWorkspaceProductConfiguration({
      workspaceId: 'ws-one',
      scopeKind: 'workspace',
      command: {
        expected_revision: 1,
        assignments: [{ pcs_id: 'guided_practice', pcs_version: '1.0.0' }],
        admission_mode: 'shadow',
        catalog_hash: 'c'.repeat(64),
      },
    });

    expect(result.snapshot_hash).toBe('b'.repeat(64));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT' });
  });

  it('surfaces 409 without retry', async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => response({ detail: { server_revision: 2 } }, 409));
    vi.stubGlobal('fetch', fetchMock);

    await expect(replaceWorkspaceProductConfiguration({
      workspaceId: 'ws-one',
      scopeKind: 'workspace',
      command: {
        expected_revision: 1,
        assignments: [],
        admission_mode: 'configuration_only',
        catalog_hash: 'c'.repeat(64),
      },
    })).rejects.toBeInstanceOf(WorkspaceProductApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
