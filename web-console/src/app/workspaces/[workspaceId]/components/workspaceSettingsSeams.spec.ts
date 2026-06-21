import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildOpenWorkspaceFolderUrl,
  buildPlaybookAutoExecConfigUrl,
  buildWorkspaceSettingsUrl,
  buildExecutionSettingsRequestPayload,
  buildStorageSettingsRequestPayload,
} from './workspaceSettingsApi';
import {
  buildIntentExtractionRequestPayload,
  buildSgrSettingsRequestPayload,
  deriveWorkspaceSettings,
  hasExecutionSettingsChanged,
  hasStorageSettingsChanged,
  toggleExpectedArtifact,
} from './workspaceSettingsState';
import type { WorkspaceSettingsWorkspace } from './workspaceSettingsTypes';

const componentsDir = dirname(fileURLToPath(import.meta.url));
const webConsoleRoot = join(componentsDir, '../../../../..');
const touchedFiles = [
  'WorkspaceSettings.tsx',
  'workspaceSettingsTypes.ts',
  'workspaceSettingsApi.ts',
  'workspaceSettingsState.ts',
  'WorkspaceSettingsExecutionSection.tsx',
  'WorkspaceSettingsStorageSection.tsx',
  'workspaceSettingsSeams.spec.ts',
];
const implementationFiles = touchedFiles.filter((fileName) => fileName !== 'workspaceSettingsSeams.spec.ts');
const passiveViewFiles = [
  'WorkspaceSettingsExecutionSection.tsx',
  'WorkspaceSettingsStorageSection.tsx',
];

function readComponentFile(fileName: string): string {
  return readFileSync(join(componentsDir, fileName), 'utf8');
}

function readWebConsoleFile(pathFromRoot: string): string {
  return readFileSync(join(webConsoleRoot, pathFromRoot), 'utf8');
}

function workspace(overrides: Partial<WorkspaceSettingsWorkspace> = {}): WorkspaceSettingsWorkspace {
  return {
    id: 'workspace-1',
    title: 'Demo',
    ...overrides,
  };
}

describe('workspace settings component seams', () => {
  it('builds existing endpoint shapes', () => {
    const context = { apiUrl: 'http://api.test', workspaceId: 'workspace-1' };

    expect(buildWorkspaceSettingsUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1');
    expect(buildOpenWorkspaceFolderUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1/open-folder');
    expect(buildPlaybookAutoExecConfigUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1/playbook-auto-exec-config');
  });

  it('builds existing request payloads', () => {
    expect(buildExecutionSettingsRequestPayload({
      executionMode: 'meeting',
      executionPriority: 'high',
      projectAssignmentMode: 'assistive',
      expectedArtifacts: ['pdf', 'md'],
    })).toEqual({
      execution_mode: 'meeting',
      execution_priority: 'high',
      project_assignment_mode: 'assistive',
      expected_artifacts: ['pdf', 'md'],
    });

    expect(buildStorageSettingsRequestPayload({
      storageBasePath: ' /tmp/mindscape ',
      artifactsDir: ' ',
    })).toEqual({
      storage_base_path: '/tmp/mindscape',
      artifacts_dir: 'artifacts',
    });

    expect(buildIntentExtractionRequestPayload({
      autoExecute: true,
      threshold: 0.7,
    })).toEqual({
      playbook_code: 'intent_extraction',
      auto_execute: true,
      confidence_threshold: 0.7,
    });

    expect(buildSgrSettingsRequestPayload(workspace({
      metadata: { existing: 'value' },
    }), {
      enabled: true,
      mode: 'two_pass',
    })).toEqual({
      metadata: {
        existing: 'value',
        sgr_enabled: true,
        sgr_mode: 'two_pass',
      },
    });
  });

  it('derives workspace settings defaults', () => {
    expect(deriveWorkspaceSettings(null)).toEqual({
      storage: {
        storageBasePath: '',
        artifactsDir: 'artifacts',
      },
      execution: {
        executionMode: 'hybrid',
        executionPriority: 'medium',
        projectAssignmentMode: 'auto_silent',
        expectedArtifacts: [],
      },
      intentExtraction: {
        autoExecute: false,
        threshold: 0.8,
      },
      sgr: {
        enabled: false,
        mode: 'inline',
      },
    });

    expect(deriveWorkspaceSettings(workspace({
      storage_base_path: '/tmp/mindscape',
      artifacts_dir: 'outputs',
      execution_mode: 'execution',
      execution_priority: 'low',
      project_assignment_mode: 'manual_first',
      expected_artifacts: ['pdf'],
      playbook_auto_execution_config: {
        intent_extraction: {
          auto_execute: true,
          confidence_threshold: 0.9,
        },
      },
      metadata: {
        sgr_enabled: true,
        sgr_mode: 'two_pass',
      },
    }))).toMatchObject({
      storage: {
        storageBasePath: '/tmp/mindscape',
        artifactsDir: 'outputs',
      },
      execution: {
        executionMode: 'execution',
        executionPriority: 'low',
        projectAssignmentMode: 'manual_first',
        expectedArtifacts: ['pdf'],
      },
      intentExtraction: {
        autoExecute: true,
        threshold: 0.9,
      },
      sgr: {
        enabled: true,
        mode: 'two_pass',
      },
    });
  });

  it('detects storage and execution dirty state without mutating artifacts', () => {
    expect(hasStorageSettingsChanged(
      { storageBasePath: '/tmp/a', artifactsDir: 'artifacts' },
      { storageBasePath: '/tmp/a', artifactsDir: 'artifacts' },
    )).toBe(false);
    expect(hasStorageSettingsChanged(
      { storageBasePath: '/tmp/b', artifactsDir: 'artifacts' },
      { storageBasePath: '/tmp/a', artifactsDir: 'artifacts' },
    )).toBe(true);

    const currentArtifacts = ['pdf', 'md'];
    const originalArtifacts = ['md', 'pdf'];
    expect(hasExecutionSettingsChanged(
      {
        executionMode: 'hybrid',
        executionPriority: 'medium',
        projectAssignmentMode: 'auto_silent',
        expectedArtifacts: currentArtifacts,
      },
      {
        executionMode: 'hybrid',
        executionPriority: 'medium',
        projectAssignmentMode: 'auto_silent',
        expectedArtifacts: originalArtifacts,
      },
    )).toBe(false);
    expect(currentArtifacts).toEqual(['pdf', 'md']);
    expect(originalArtifacts).toEqual(['md', 'pdf']);
  });

  it('toggles expected artifact values', () => {
    expect(toggleExpectedArtifact(['pdf'], 'md')).toEqual(['pdf', 'md']);
    expect(toggleExpectedArtifact(['pdf', 'md'], 'pdf')).toEqual(['md']);
  });

  it('keeps touched component files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readComponentFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps API ownership in the API helper', () => {
    const apiSource = readComponentFile('workspaceSettingsApi.ts');
    expect(apiSource).toContain('fetch(');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/open-folder');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config');

    for (const fileName of implementationFiles.filter((name) => name !== 'workspaceSettingsApi.ts')) {
      const source = readComponentFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('/api/v1/');
    }
  });

  it('keeps section views resource passive', () => {
    for (const fileName of passiveViewFiles) {
      const source = readComponentFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('/api/v1/');
      expect(source, fileName).not.toContain('setTimeout(');
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('AbortController');
      expect(source, fileName).not.toContain('localStorage');
      expect(source, fileName).not.toContain('sessionStorage');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toMatch(/\bpoll/i);
    }
  });

  it('does not introduce a live WorkspaceSettings caller', () => {
    const providerSource = readWebConsoleFile('src/app/workspaces/[workspaceId]/components/WorkspaceGlobalToolRailProvider.tsx');
    const providerCoreSource = readWebConsoleFile('src/app/workspaces/[workspaceId]/components/workspaceGlobalToolRailCoreContributions.tsx');
    const runtimeFrameSource = readWebConsoleFile('src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityHostRuntimeFrame.tsx');

    expect(providerSource).toContain("from './workspaceGlobalToolRailCoreContributions'");
    expect(providerCoreSource).toContain("import('../capability-ui-hosts/WorkspaceSettingsToolPanel')");
    expect(runtimeFrameSource).toContain("import('./WorkspaceSettingsToolPanel')");
    expect(providerSource).not.toContain("import('./WorkspaceSettings')");
    expect(providerCoreSource).not.toContain("import('./WorkspaceSettings')");
    expect(runtimeFrameSource).not.toContain('components/WorkspaceSettings');
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readComponentFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
