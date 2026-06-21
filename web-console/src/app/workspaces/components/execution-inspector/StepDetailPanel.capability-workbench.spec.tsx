import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import React from 'react';
import { describe, expect, it } from 'vitest';

import type { ExecutionStep } from './types/execution';
import StepDetailPanel, {
  type StepDetailPanelProps,
} from './StepDetailPanel';
import {
  buildCapabilityWorkbenchHref,
  capabilitySupportsWorkbenchRoute,
} from './StepDetailPanel';

const inspectorDir = path.join(
  process.cwd(),
  'src/app/workspaces/components/execution-inspector',
);
const seamDir = path.join(inspectorDir, 'stepDetailPanel');

const sampleStep: ExecutionStep = {
  id: 'step-1',
  execution_id: 'execution-1',
  step_index: 0,
  step_name: 'Prepare assets',
  status: 'completed',
  step_type: 'tool',
  requires_confirmation: false,
  description: 'Prepare source materials',
};

function translate(key: string, params?: any): string {
  if (key === 'stepNumber') {
    return `Step ${params?.number}`;
  }
  if (key === 'artifacts' || key === 'noArtifacts') {
    return '';
  }
  return key;
}

describe('StepDetailPanel capability workbench link', () => {
  it('builds canonical workbench hrefs for review bundle artifacts', () => {
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: 'ws demo',
        capabilityCode: 'performance_direction',
        artifactId: 'artifact 001',
        runId: 'run 001',
        sceneId: 'scene 001',
      }),
    ).toBe(
      '/workspaces/ws%20demo/capability-ui-hosts/performance_direction?artifact_id=artifact+001&run_id=run+001&scene_id=scene+001',
    );
  });

  it('does not build a link without both workspace and capability code', () => {
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: '',
        capabilityCode: 'performance_direction',
        artifactId: 'artifact_001',
      }),
    ).toBeNull();
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: 'ws_demo',
        capabilityCode: null,
        artifactId: 'artifact_001',
      }),
    ).toBeNull();
  });

  it('requires installed capability metadata with UI components before showing workbench routes', () => {
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'performance_direction',
            ui_components: [{ code: 'PerformanceDirectionStoryboardEditorPage' }],
          },
        ],
        'performance_direction',
      ),
    ).toBe(true);
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'performance_direction',
            ui_components: [],
          },
        ],
        'performance_direction',
      ),
    ).toBe(false);
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'ig',
            ui_components: [{ code: 'IGWorkbenchPage' }],
          },
        ],
        'performance_direction',
      ),
    ).toBe(false);
  });
});

describe('StepDetailPanel render seam', () => {
  it('renders the selected step without starting capability cache loading', () => {
    const props: StepDetailPanelProps = {
      steps: [sampleStep],
      totalSteps: 1,
      currentStepIndex: 1,
      currentStepToolCalls: [],
      stepEvents: [],
      artifacts: [],
      t: translate,
    };

    render(<StepDetailPanel {...props} />);

    expect(screen.getByText('Step 1: Prepare assets')).toBeInTheDocument();
    expect(screen.getByText('Prepare source materials')).toBeInTheDocument();
    expect(screen.getByText('This step has not produced artifacts yet')).toBeInTheDocument();
  });
});

describe('StepDetailPanel seam boundaries', () => {
  it('keeps touched files below the line gate', () => {
    const files = [
      'StepDetailPanel.tsx',
      'StepDetailPanel.capability-workbench.spec.tsx',
      'stepDetailPanel/ArtifactsSection.tsx',
      'stepDetailPanel/DynamicCapabilityComponentsSection.tsx',
      'stepDetailPanel/RemoteExecutionSection.tsx',
      'stepDetailPanel/StepDetailPanelView.tsx',
      'stepDetailPanel/StepEventsSection.tsx',
      'stepDetailPanel/StepHeaderSection.tsx',
      'stepDetailPanel/ToolCallsSection.tsx',
      'stepDetailPanel/VisualAcceptanceSection.tsx',
      'stepDetailPanel/stepDetailPanelState.ts',
      'stepDetailPanel/stepDetailPanelTypes.ts',
    ];

    for (const file of files) {
      const lineCount = readFileSync(path.join(inspectorDir, file), 'utf8').split('\n').length;
      expect(lineCount, file).toBeLessThanOrEqual(500);
    }
  });

  it('keeps resource loading ownership in the public wrapper', () => {
    const publicWrapper = readFileSync(path.join(inspectorDir, 'StepDetailPanel.tsx'), 'utf8');
    expect(publicWrapper).toContain('getInstalledCapabilities(apiUrl)');
    expect(publicWrapper).toContain("import('@/lib/capability-ui-loader')");

    const passiveFiles = [
      'ArtifactsSection.tsx',
      'DynamicCapabilityComponentsSection.tsx',
      'RemoteExecutionSection.tsx',
      'StepDetailPanelView.tsx',
      'StepEventsSection.tsx',
      'StepHeaderSection.tsx',
      'ToolCallsSection.tsx',
      'VisualAcceptanceSection.tsx',
      'stepDetailPanelState.ts',
      'stepDetailPanelTypes.ts',
    ];

    for (const file of passiveFiles) {
      const content = readFileSync(path.join(seamDir, file), 'utf8');
      expect(content, file).not.toMatch(
        /fetch\(|setInterval|setTimeout|AbortSignal|EventSource|WebSocket|worker|queue|pgbouncer|postgres|pool|poll|Promise\.all|localStorage|sessionStorage|window\.|navigator\./,
      );
    }
  });

  it('preserves the default caller and public helper export surface', () => {
    const executionInspector = readFileSync(
      path.join(inspectorDir, '../ExecutionInspector.tsx'),
      'utf8',
    );
    const publicWrapper = readFileSync(path.join(inspectorDir, 'StepDetailPanel.tsx'), 'utf8');

    expect(executionInspector).toContain("import StepDetailPanel from './execution-inspector/StepDetailPanel'");
    expect(publicWrapper).toContain('export default function StepDetailPanel');
    expect(publicWrapper).toContain('buildCapabilityWorkbenchHref');
    expect(publicWrapper).toContain('capabilitySupportsWorkbenchRoute');
  });
});
