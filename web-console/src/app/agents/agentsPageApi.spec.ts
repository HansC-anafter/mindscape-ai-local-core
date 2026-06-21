import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildBackendConfigUrl,
  buildPlaybooksUrl,
  buildRunAgentUrl,
  buildRunAllAgentsUrl,
  loadBackendAvailability,
  loadSuggestedPlaybookCodes,
  runAgentRequest,
  runAllAgentsRequest,
} from './agentsPageApi';

const routeDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'page.tsx',
  'AgentsSelectedRolePanel.tsx',
  'agentsPageApi.ts',
  'agentsPageApi.spec.ts',
];
const implementationFiles = touchedFiles.filter((fileName) => fileName !== 'agentsPageApi.spec.ts');

function readRouteFile(fileName: string): string {
  return readFileSync(join(routeDir, fileName), 'utf8');
}

function jsonResponse(data: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(data),
  } as Response);
}

describe('agents page API seam', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the existing endpoint shapes', () => {
    expect(buildBackendConfigUrl('profile-a', '')).toBe('/api/v1/config/backend?profile_id=profile-a');
    expect(buildBackendConfigUrl('profile-a', 'http://api.test')).toBe(
      'http://api.test/api/v1/config/backend?profile_id=profile-a'
    );
    expect(buildPlaybooksUrl('')).toBe('/api/v1/playbooks');
    expect(buildRunAgentUrl('profile-a', '')).toBe('/api/v1/agent/run?profile_id=profile-a');
    expect(buildRunAllAgentsUrl('profile-a', '')).toBe('/api/v1/agent/run-all?profile_id=profile-a');
  });

  it('loads backend availability without changing the config endpoint', async () => {
    const fetchMock = vi.fn(() => jsonResponse({
      current_mode: 'local',
      available_backends: {
        local: { available: true },
      },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadBackendAvailability('http://api.test', 'profile-a')).resolves.toEqual({
      backendAvailable: true,
      missingApiKey: false,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/config/backend?profile_id=profile-a',
      { headers: { 'Content-Type': 'application/json' } }
    );
  });

  it('reports missing API key when the selected backend is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({
      current_mode: 'local',
      available_backends: {
        local: { available: false },
      },
    })));

    await expect(loadBackendAvailability('', 'profile-a')).resolves.toEqual({
      backendAvailable: false,
      missingApiKey: true,
    });
  });

  it('loads the first three suggested playbook codes', async () => {
    const fetchMock = vi.fn(() => jsonResponse([
      { metadata: { playbook_code: 'book-one' } },
      { metadata: { playbook_code: 'book-two' } },
      { metadata: { playbook_code: 'book-three' } },
      { metadata: { playbook_code: 'book-four' } },
    ]));
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadSuggestedPlaybookCodes('http://api.test')).resolves.toEqual([
      'book-one',
      'book-two',
      'book-three',
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/playbooks',
      { headers: { 'Content-Type': 'application/json' } }
    );
  });

  it('submits a single agent run with the preserved payload shape', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => jsonResponse({ output: 'done', status: 'completed' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(runAgentRequest({
      task: 'Plan a launch',
      agentType: 'planner',
      agentTypeDescription: '',
      useMindscape: true,
    }, 'profile-a', 'http://api.test')).resolves.toEqual({ output: 'done', status: 'completed' });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/agent/run?profile_id=profile-a',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(requestInit.body))).toEqual({
      task: 'Plan a launch',
      agent_type: 'planner',
      use_mindscape: true,
      intent_ids: [],
    });
  });

  it('submits all-agents runs and propagates backend error detail', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => jsonResponse({ detail: 'No LLM providers configured' }, false));
    vi.stubGlobal('fetch', fetchMock);

    await expect(runAllAgentsRequest({
      task: 'Compare launch plans',
      useMindscape: false,
    }, 'profile-a', '')).rejects.toThrow('No LLM providers configured');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/agent/run-all?profile_id=profile-a',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(requestInit.body))).toEqual({
      task: 'Compare launch plans',
      agent_type: 'planner',
      use_mindscape: false,
      intent_ids: [],
    });
  });

  it('keeps touched route files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps the page free of raw request ownership', () => {
    const pageSource = readRouteFile('page.tsx');
    const viewSource = readRouteFile('AgentsSelectedRolePanel.tsx');
    expect(pageSource).not.toMatch(/\bfetch\s*\(/);
    expect(viewSource).not.toMatch(/\bfetch\s*\(/);
    expect(viewSource).not.toContain('/api/v1/');

    for (const fileName of implementationFiles) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('setTimeout(');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('localStorage');
      expect(source, fileName).not.toContain('sessionStorage');
    }
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readRouteFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
