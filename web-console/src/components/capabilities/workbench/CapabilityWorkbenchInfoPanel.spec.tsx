import '@testing-library/jest-dom/vitest';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CapabilityWorkbenchInfoPanel } from './CapabilityWorkbenchInfoPanel';
import type { CapabilityWorkbenchInfoMetadata } from '@/types/capability-workbench';

const METADATA: CapabilityWorkbenchInfoMetadata = {
  schemaVersion: 'capability_workbench_info_metadata.v1',
  capability: {
    code: 'demo_capability',
    label: 'Demo Capability',
  },
  workspace: {
    id: 'ws_demo',
  },
  primaryObject: {
    kind: 'artifact',
    id: 'asset_demo',
    label: 'Asset demo',
    ownerCapability: 'demo_capability',
  },
  session: {
    id: 'session_demo',
    kind: 'demo_session',
    status: 'active',
  },
  artifact: {
    id: 'artifact_demo',
    kind: 'demo_artifact',
  },
  selection: {
    sceneId: 'item01',
    mode: 'inspect',
    department: 'review',
  },
  references: [
    {
      key: 'asset',
      label: 'Asset',
      value: 'asset_demo',
      copyValue: 'asset_demo',
    },
  ],
  status: [
    {
      key: 'blocked_decisions',
      label: 'Blocked decisions',
      value: '2',
      tone: 'warning',
    },
  ],
};

describe('CapabilityWorkbenchInfoPanel', () => {
  it('renders the canonical metadata sections and copy rows', () => {
    const writeText = vi.fn();
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });

    render(<CapabilityWorkbenchInfoPanel metadata={METADATA} />);

    expect(screen.getByTestId('capability-workbench-info-panel')).toBeInTheDocument();
    expect(screen.getByText('Demo Capability')).toBeInTheDocument();
    expect(screen.getByText('demo_capability')).toBeInTheDocument();
    expect(screen.getByText('artifact:asset_demo')).toBeInTheDocument();
    expect(screen.getByText('session_demo')).toBeInTheDocument();
    expect(screen.getByText('inspect / review / item01')).toBeInTheDocument();
    expect(screen.getByText('Blocked decisions')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith('asset_demo');
  });

  it('renders a contract error instead of a pack-specific fallback for invalid metadata', () => {
    render(<CapabilityWorkbenchInfoPanel metadata={{ schemaVersion: 'bad' } as any} />);

    expect(screen.getByTestId('capability-workbench-info-invalid')).toHaveTextContent(
      'Invalid workbench info metadata contract.',
    );
  });
});
