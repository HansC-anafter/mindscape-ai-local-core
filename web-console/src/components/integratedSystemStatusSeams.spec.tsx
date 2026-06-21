import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildMcpGatewayHealthUrl,
  buildWorkspaceAgentsUrl,
  buildXttsHealthUrl,
  fetchAgentsStatus,
  fetchHostServicesStatus,
  shouldSkipBackgroundPoll,
} from './integratedSystemStatusApi';
import {
  DEFAULT_UNIX_BRIDGE_COMMAND,
  DEFAULT_WINDOWS_BRIDGE_COMMAND,
  formatProviderName,
  HOST_SERVICE_TIMEOUT_MS,
  POLL_INTERVAL_MS,
} from './integratedSystemStatusTypes';

const componentsDir = dirname(fileURLToPath(import.meta.url));
const webConsoleRoot = join(componentsDir, '..');
const touchedFiles = [
  'IntegratedSystemStatusCard.tsx',
  'IntegratedSystemStatusCardView.tsx',
  'integratedSystemStatusApi.ts',
  'integratedSystemStatusTypes.ts',
  'integratedSystemStatusSeams.spec.tsx',
];

function readComponentFile(fileName: string): string {
  return readFileSync(join(componentsDir, fileName), 'utf8');
}

function readWebConsoleFile(pathFromSrc: string): string {
  return readFileSync(join(webConsoleRoot, pathFromSrc), 'utf8');
}

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 503,
    json: async () => payload,
  } as Response;
}

describe('integrated system status seams', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds existing endpoint shapes and preserves constants', () => {
    expect(buildWorkspaceAgentsUrl('http://api.test', 'workspace-1'))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/agents');
    expect(buildXttsHealthUrl('http://api.test')).toBe('http://api.test/api/v1/host/services/xtts/health');
    expect(buildMcpGatewayHealthUrl('http://api.test')).toBe('http://api.test/api/v1/host/services/mcp-gateway/health');
    expect(POLL_INTERVAL_MS).toBe(30_000);
    expect(HOST_SERVICE_TIMEOUT_MS).toBe(3_000);
    expect(DEFAULT_WINDOWS_BRIDGE_COMMAND).toBe('.\\scripts\\start_cli_bridge.ps1 -All');
    expect(DEFAULT_UNIX_BRIDGE_COMMAND).toBe('./scripts/start_cli_bridge.sh --all');
  });

  it('normalizes agents responses without clearing existing state on failures', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      agents: [{ id: 'agent-1', name: 'Gemini', status: 'available', transport: 'ws' }],
      bridge_script_path: '/repo/scripts/start_cli_bridge.sh',
    }));

    await expect(fetchAgentsStatus('workspace-1', 'http://api.test', fetchMock)).resolves.toEqual({
      agents: [{ id: 'agent-1', name: 'Gemini', status: 'available', transport: 'ws' }],
      bridgeScriptPath: '/repo/scripts/start_cli_bridge.sh',
    });
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/workspace-1/agents');

    await expect(fetchAgentsStatus('workspace-1', 'http://api.test', vi.fn(async () => jsonResponse({}, false))))
      .resolves.toBeNull();
  });

  it('normalizes host service status checks', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', model_loaded: true }))
      .mockResolvedValueOnce(jsonResponse({}, true));

    await expect(fetchHostServicesStatus('http://api.test', fetchMock)).resolves.toEqual([
      { name: 'XTTS Service', ok: true, detail: 'model loaded' },
      { name: 'MCP Gateway', ok: true, detail: 'running' },
    ]);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://api.test/api/v1/host/services/xtts/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://api.test/api/v1/host/services/mcp-gateway/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    const failedFetch = vi.fn(async () => {
      throw new Error('offline');
    });
    await expect(fetchHostServicesStatus('http://api.test', failedFetch)).resolves.toEqual([
      { name: 'XTTS Service', ok: false, detail: 'unreachable' },
      { name: 'MCP Gateway', ok: false, detail: 'unreachable' },
    ]);
  });

  it('keeps hidden-tab skip and provider formatting behavior', () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    expect(shouldSkipBackgroundPoll()).toBe(true);

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    expect(shouldSkipBackgroundPoll()).toBe(false);
    expect(formatProviderName('vertex_ai')).toBe('Vertex AI');
    expect(formatProviderName('remote-crs')).toBe('Remote crs');
  });

  it('keeps touched component files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readComponentFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps API ownership in the API helper and live timing in the wrapper', () => {
    const apiSource = readComponentFile('integratedSystemStatusApi.ts');
    expect(apiSource).toContain('fetchImpl(');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/agents');
    expect(apiSource).toContain('/api/v1/host/services/xtts/health');
    expect(apiSource).toContain('/api/v1/host/services/mcp-gateway/health');

    const wrapperSource = readComponentFile('IntegratedSystemStatusCard.tsx');
    expect(wrapperSource).toContain('setInterval(() => {');
    expect(wrapperSource).toContain('clearInterval(interval)');
    expect(wrapperSource).toContain('setTimeout(() => setCopied(false), COPY_RESET_MS)');
    expect(wrapperSource).toContain('setTimeout(() => setCopiedAll(false), COPY_RESET_MS)');
    expect(wrapperSource).toContain('agentsRequestRef');
    expect(wrapperSource).toContain('hostServicesRequestRef');
  });

  it('keeps passive view free of resource owner markers', () => {
    const source = readComponentFile('IntegratedSystemStatusCardView.tsx');
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).not.toContain('/api/v1/');
    expect(source).not.toContain('setTimeout(');
    expect(source).not.toContain('setInterval(');
    expect(source).not.toContain('AbortController');
    expect(source).not.toContain('AbortSignal');
    expect(source).not.toContain('navigator.');
    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('sessionStorage');
    expect(source).not.toContain('EventSource');
    expect(source).not.toContain('WebSocket');
    expect(source).not.toMatch(/\bpoll/i);
  });

  it('does not add a production caller or mount path', () => {
    const selfSource = readComponentFile('IntegratedSystemStatusCard.tsx');
    expect(selfSource).toContain('export default function IntegratedSystemStatusCard');

    const workspaceRootFiles = [
      'app/workspaces/[workspaceId]/page.tsx',
      'app/workspaces/[workspaceId]/layout.tsx',
      'app/workspaces/[workspaceId]/home/page.tsx',
      'app/workspaces/[workspaceId]/components/WorkspaceSettings.tsx',
      'app/workspaces/[workspaceId]/components/ProjectsPanel.tsx',
    ];
    for (const fileName of workspaceRootFiles) {
      expect(readWebConsoleFile(fileName), fileName).not.toContain('IntegratedSystemStatusCard');
    }
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readComponentFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
