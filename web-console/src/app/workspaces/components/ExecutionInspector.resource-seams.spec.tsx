import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  applyReviewBundleArtifactUpdate,
  deriveExecutionThreadId,
  extractProductionRunId,
  filterArtifactsForExecution,
  filterReviewBundlesForRun,
  getLatestArtifact,
  toArtifactRecord,
} from './execution-inspector/executionInspector/executionInspectorState';
import type {
  Artifact,
  ExecutionSession,
  ReviewBundleArtifact,
} from './execution-inspector/types/execution';

const workspaceRoot = process.cwd();
const componentDir = path.join(workspaceRoot, 'src/app/workspaces/components');
const seamDir = path.join(componentDir, 'execution-inspector/executionInspector');

describe('ExecutionInspector helper seams', () => {
  it('preserves artifact URL and record conversion', () => {
    const record = toArtifactRecord({
      id: 'artifact-1',
      title: 'Report',
      type: 'document',
      file_path: '/tmp/report.md',
      created_at: '2026-06-21T00:00:00Z',
      metadata: { step_id: 'step-1' },
      execution_id: 'execution-1',
    }, 'http://api.test', 'workspace-1');

    expect(record).toMatchObject({
      id: 'artifact-1',
      name: 'Report',
      type: 'document',
      stepId: 'step-1',
      url: 'http://api.test/api/v1/workspaces/workspace-1/artifacts/artifact-1/file',
    });
  });

  it('filters execution artifacts by execution metadata and keeps endpoint conversion', () => {
    const artifacts = filterArtifactsForExecution([
      { id: 'a1', title: 'A1', execution_id: 'execution-1', metadata: {} },
      { id: 'a2', title: 'A2', metadata: { navigate_to: 'execution-2' } },
      { id: 'a3', title: 'A3', metadata: { execution_id: 'execution-1' }, external_url: 'https://example.test/a3' },
    ], 'http://api.test', 'workspace-1', 'execution-1');

    expect(artifacts.map((artifact) => artifact.id)).toEqual(['a1', 'a3']);
    expect(artifacts[1].url).toBe('https://example.test/a3');
  });

  it('keeps production run id and thread id derivation priority stable', () => {
    const execution = {
      execution_id: 'execution-1',
      workspace_id: 'workspace-1',
      status: 'running',
      current_step_index: 0,
      total_steps: 3,
      execution_context: {
        inputs: { run_id: 'input-run', thread_id: 'input-thread' },
        run_id: 'execution-run',
        workflow_result: { outputs: { run_id: 'workflow-output-run' } },
      },
      task: {
        result: { outputs: { run_id: 'task-output-run' } },
        execution_context: { run_id: 'task-context-run' },
        params: { run_id: 'task-param-run' },
      },
      thread_id: 'execution-thread',
    } as ExecutionSession;

    expect(extractProductionRunId(execution)).toBe('task-output-run');
    expect(deriveExecutionThreadId(execution)).toBe('input-thread');
  });

  it('filters review bundles by run id and sorts newest first', () => {
    const bundles = filterReviewBundlesForRun([
      { id: 'old', title: 'Old', metadata: { run_id: 'run-1' }, created_at: '2026-06-20T00:00:00Z' },
      { id: 'skip', title: 'Skip', metadata: { run_id: 'run-2' }, created_at: '2026-06-22T00:00:00Z' },
      { id: 'new', title: 'New', content: { run_id: 'run-1' }, created_at: '2026-06-21T00:00:00Z' },
    ], 'http://api.test', 'workspace-1', 'run-1');

    expect(bundles.map((bundle) => bundle.id)).toEqual(['new', 'old']);
  });

  it('updates an existing review bundle or prepends a new one', () => {
    const current = [
      { id: 'bundle-1', name: 'Old', type: 'bundle' },
    ] as ReviewBundleArtifact[];
    const updated = { id: 'bundle-1', name: 'Updated', type: 'bundle' } as ReviewBundleArtifact;
    const inserted = { id: 'bundle-2', name: 'Inserted', type: 'bundle' } as ReviewBundleArtifact;

    expect(applyReviewBundleArtifactUpdate(current, updated)).toEqual([updated]);
    expect(applyReviewBundleArtifactUpdate(current, inserted)).toEqual([inserted, current[0]]);
  });

  it('returns the newest artifact by created timestamp', () => {
    const artifacts = [
      { id: 'old', name: 'Old', type: 'doc', createdAt: '2026-06-20T00:00:00Z' },
      { id: 'new', name: 'New', type: 'doc', createdAt: '2026-06-21T00:00:00Z' },
    ] as Artifact[];

    expect(getLatestArtifact(artifacts)?.id).toBe('new');
    expect(getLatestArtifact([])).toBeUndefined();
  });
});

describe('ExecutionInspector seam boundaries', () => {
  it('keeps touched files below the line gate', () => {
    const files = [
      'ExecutionInspector.tsx',
      'ExecutionInspector.resource-seams.spec.tsx',
      'execution-inspector/executionInspector/ExecutionInspectorView.tsx',
      'execution-inspector/executionInspector/executionInspectorState.ts',
      'execution-inspector/executionInspector/useExecutionArtifacts.ts',
      'execution-inspector/executionInspector/useRelatedGovernedMemory.ts',
      'execution-inspector/executionInspector/useReviewBundleArtifacts.ts',
    ];

    for (const file of files) {
      const lineCount = readFileSync(path.join(componentDir, file), 'utf8').split('\n').length;
      expect(lineCount, file).toBeLessThanOrEqual(500);
    }
  });

  it('keeps raw fetch ownership in the three planned hooks only', () => {
    const hookFiles = [
      'useExecutionArtifacts.ts',
      'useRelatedGovernedMemory.ts',
      'useReviewBundleArtifacts.ts',
    ];
    for (const file of hookFiles) {
      const source = readFileSync(path.join(seamDir, file), 'utf8');
      expect(source, file).toContain('fetch(');
    }

    const passiveFiles = [
      path.join(componentDir, 'ExecutionInspector.tsx'),
      path.join(seamDir, 'ExecutionInspectorView.tsx'),
      path.join(seamDir, 'executionInspectorState.ts'),
    ];
    for (const file of passiveFiles) {
      const source = readFileSync(file, 'utf8');
      expect(source, file).not.toContain('fetch(');
      expect(source, file).not.toContain('setInterval');
      expect(source, file).not.toContain('EventSource');
      expect(source, file).not.toContain('WebSocket');
    }
  });

  it('keeps the production route on the root public component', () => {
    const routeSource = readFileSync(
      path.join(workspaceRoot, 'src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx'),
      'utf8',
    );

    expect(routeSource).toContain("import ExecutionInspector from '../../../components/ExecutionInspector'");
  });
});
