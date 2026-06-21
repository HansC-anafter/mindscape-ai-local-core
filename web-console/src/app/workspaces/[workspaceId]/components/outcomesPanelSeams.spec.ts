import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildArtifactCopyUrl,
  buildArtifactExternalUrl,
  buildArtifactFileUrl,
  buildArtifactListUrl,
  buildCapabilityComponentUrl,
  buildExecutionDetailUrl,
  buildExecutionSandboxUrl,
  clearArtifactListRequestCache,
  fetchWorkspaceArtifacts,
} from './outcomesPanelApi';
import {
  artifactsMatchComponent,
  collectMatchingComponents,
  extractSandboxIdFromPath,
  getArtifactIcon,
  resolveArtifactDisplayInfo,
  resolveSandboxOpenTarget,
} from './outcomesPanelState';
import type { Artifact } from './outcomesPanelTypes';

const componentsDir = dirname(fileURLToPath(import.meta.url));
const webConsoleRoot = join(componentsDir, '../../../../..');
const touchedFiles = [
  'OutcomesPanel.tsx',
  'OutcomesPanelView.tsx',
  'outcomesPanelApi.ts',
  'outcomesPanelState.ts',
  'outcomesPanelTypes.ts',
  'outcomesPanelSeams.spec.ts',
];

function readComponentFile(fileName: string): string {
  return readFileSync(join(componentsDir, fileName), 'utf8');
}

function readWebConsoleFile(pathFromRoot: string): string {
  return readFileSync(join(webConsoleRoot, pathFromRoot), 'utf8');
}

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: 'artifact-1',
    workspace_id: 'workspace-1',
    playbook_code: 'demo_playbook',
    artifact_type: 'draft',
    title: 'Draft outcome',
    summary: 'Summary',
    content: {},
    primary_action_type: 'download',
    metadata: {},
    created_at: '2026-06-21T00:00:00Z',
    updated_at: '2026-06-21T00:00:00Z',
    ...overrides,
  };
}

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    statusText: ok ? 'OK' : 'Service Unavailable',
    json: async () => payload,
  } as Response;
}

describe('outcomes panel seams', () => {
  afterEach(() => {
    clearArtifactListRequestCache();
    vi.restoreAllMocks();
  });

  it('builds existing endpoint and navigation shapes', () => {
    expect(buildArtifactListUrl('http://api.test', 'workspace-1'))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/artifacts?include_content=false&include_preview=false&limit=100');
    expect(buildArtifactCopyUrl('http://api.test', 'workspace-1', 'artifact-1'))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/artifacts/artifact-1/copy');
    expect(buildArtifactCopyUrl('http://api.test', 'workspace-1', 'artifact-1', true))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/artifacts/artifact-1/copy?force=true');
    expect(buildArtifactExternalUrl('http://api.test', 'workspace-1', 'artifact-1'))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/artifacts/artifact-1/external-url');
    expect(buildArtifactFileUrl('http://api.test', 'workspace-1', 'artifact-1'))
      .toBe('http://api.test/api/v1/workspaces/workspace-1/artifacts/artifact-1/file');
    expect(buildCapabilityComponentUrl('workspace-1', 'capability', 'Workbench Card'))
      .toBe('/workspaces/workspace-1/capabilities/capability/ui?component=Workbench%20Card');
    expect(buildExecutionDetailUrl('workspace-1', 'execution-1')).toBe('/workspaces/workspace-1/executions/execution-1');
    expect(buildExecutionSandboxUrl('workspace-1', 'sandbox-1')).toBe('/workspaces/workspace-1/executions?sandbox=sandbox-1');
  });

  it('dedupes artifact list fetches by api and workspace', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ artifacts: [artifact()] }));

    const first = fetchWorkspaceArtifacts('http://api.test', 'workspace-1', fetchMock);
    const second = fetchWorkspaceArtifacts('http://api.test', 'workspace-1', fetchMock);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(first).resolves.toHaveLength(1);
    await expect(second).resolves.toHaveLength(1);

    await fetchWorkspaceArtifacts('http://api.test', 'workspace-1', fetchMock);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('preserves artifact matching and icon behavior', () => {
    const artifacts = [
      artifact({ artifact_type: 'draft', playbook_code: 'demo' }),
      artifact({ id: 'artifact-2', artifact_type: 'audio', playbook_code: 'voice' }),
    ];

    expect(getArtifactIcon('draft')).toBe('DOC');
    expect(getArtifactIcon('unknown')).toBe('ITEM');
    expect(artifactsMatchComponent(artifacts, { code: 'DraftCard', artifact_types: ['draft'] })).toBe(true);
    expect(artifactsMatchComponent(artifacts, { code: 'VoiceCard', playbook_codes: ['voice'] })).toBe(true);
    expect(artifactsMatchComponent(artifacts, { code: 'SomeWorkbench', artifact_types: ['draft'] })).toBe(false);
    expect(artifactsMatchComponent(artifacts, { code: 'SomePage', artifact_types: ['draft'] })).toBe(false);

    expect(collectMatchingComponents(artifacts, [{
      code: 'capability_a',
      ui_components: [
        { code: 'DraftCard', artifact_types: ['draft'], description: 'Drafts' },
        { code: 'IgnoredWorkbench', artifact_types: ['draft'] },
      ],
    }])).toEqual([{
      key: 'capability_a:DraftCard',
      capabilityCode: 'capability_a',
      componentCode: 'DraftCard',
      description: 'Drafts',
    }]);
  });

  it('preserves display and sandbox target derivation', () => {
    const withProjectRepoPath = artifact({
      content: { file_name: 'report.md' },
      metadata: {
        actual_file_path: '/app/data/sandboxes/workspace-1/project_repo/sandbox-1/current/reports/report.md',
        execution_id: 'execution-1',
      },
    });

    expect(resolveArtifactDisplayInfo(withProjectRepoPath)).toMatchObject({
      fileName: 'report.md',
      executionId: 'execution-1',
    });
    expect(resolveSandboxOpenTarget(withProjectRepoPath, 'execution-1')).toEqual({
      sandboxId: 'sandbox-1',
      relativeFilePath: 'reports/report.md',
      executionId: 'execution-1',
    });

    expect(resolveSandboxOpenTarget(artifact({
      metadata: {
        actual_file_path: '/app/data/sandboxes/workspace-1/group/sandbox-2/current/out.txt',
        execution_id: 'execution-2',
      },
    }), null)).toEqual({
      sandboxId: 'sandbox-2',
      relativeFilePath: 'out.txt',
      executionId: 'execution-2',
    });
    expect(extractSandboxIdFromPath('/tmp/sandboxes/sandbox-3/file.txt')).toBe('sandbox-3');
  });

  it('keeps touched files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readComponentFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps resource owners in the wrapper and API only', () => {
    const wrapperSource = readComponentFile('OutcomesPanel.tsx');
    expect(wrapperSource).toContain("window.addEventListener('workspace-chat-updated'");
    expect(wrapperSource).toContain("window.removeEventListener('workspace-chat-updated'");
    expect(wrapperSource).toContain('setTimeout(() => {');
    expect(wrapperSource).toContain('clearTimeout(debounceTimer)');
    expect(wrapperSource).toContain('navigator.clipboard.writeText');
    expect(wrapperSource).toContain('window.open(');
    expect(wrapperSource).toContain('loadArtifactsInFlightRef');

    const apiSource = readComponentFile('outcomesPanelApi.ts');
    expect(apiSource).toContain('fetchImpl(buildArtifactListUrl');
    expect(apiSource).toContain('artifactListRequests');

    for (const fileName of ['OutcomesPanelView.tsx', 'outcomesPanelState.ts']) {
      const source = readComponentFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('setTimeout(');
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('addEventListener');
      expect(source, fileName).not.toContain('removeEventListener');
      expect(source, fileName).not.toContain('navigator.');
      expect(source, fileName).not.toContain('window.open');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toMatch(/\bpoll/i);
    }
  });

  it('preserves public default callers and Artifact type consumers', () => {
    const publicModule = readComponentFile('OutcomesPanel.tsx');
    expect(publicModule).toContain('export default function OutcomesPanel');
    expect(publicModule).toContain("export type { Artifact } from './outcomesPanelTypes'");

    const timelineSections = readWebConsoleFile('src/app/workspaces/components/timeline/TimelineExecutionSections.tsx');
    const defaultLeftSidebar = readWebConsoleFile('src/components/playbooks/DefaultLeftSidebar.tsx');
    expect(timelineSections).toContain("import OutcomesPanel from '../../[workspaceId]/components/OutcomesPanel'");
    expect(defaultLeftSidebar).toContain("import OutcomesPanel from '../../app/workspaces/[workspaceId]/components/OutcomesPanel'");
    expect(timelineSections).toContain('<OutcomesPanel');
    expect(defaultLeftSidebar).toContain('<OutcomesPanel');

    expect(readWebConsoleFile('src/app/workspaces/[workspaceId]/WorkspacePageClient.tsx'))
      .toContain("from './components/OutcomesPanel'");
    for (const pathFromRoot of [
      'src/app/workspaces/[workspaceId]/components/WorkspaceModals.tsx',
      'src/app/workspaces/[workspaceId]/components/WorkspaceRightSidebar.tsx',
      'src/app/workspaces/[workspaceId]/components/OutcomeCard.tsx',
    ]) {
      expect(readWebConsoleFile(pathFromRoot), pathFromRoot).toContain("from './OutcomesPanel'");
    }
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readComponentFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
