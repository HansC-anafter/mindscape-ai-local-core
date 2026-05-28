import '@testing-library/jest-dom/vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { CapabilityWorkbenchInfoMetadata } from '@/types/capability-workbench';
import {
  CapabilityWorkbenchInfoProvider,
  useCapabilityWorkbenchInfoMetadata,
  useCapabilityWorkbenchInfoMetadataRegistration,
} from './CapabilityWorkbenchInfoProvider';

function metadata(id: string): CapabilityWorkbenchInfoMetadata {
  return {
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
      id,
    },
    references: [],
    status: [],
  };
}

function RegisteringChild({
  value,
}: {
  value: CapabilityWorkbenchInfoMetadata | null;
}) {
  useCapabilityWorkbenchInfoMetadataRegistration(value);
  return null;
}

function MetadataReader() {
  const registeredMetadata = useCapabilityWorkbenchInfoMetadata();
  return (
    <div data-testid="active-metadata">
      {registeredMetadata?.primaryObject.id || 'none'}
    </div>
  );
}

describe('CapabilityWorkbenchInfoProvider', () => {
  it('registers, updates, and clears active metadata', async () => {
    const { rerender } = render(
      <CapabilityWorkbenchInfoProvider>
        <RegisteringChild value={metadata('sb_one')} />
        <MetadataReader />
      </CapabilityWorkbenchInfoProvider>,
    );

    await screen.findByText('sb_one');

    rerender(
      <CapabilityWorkbenchInfoProvider>
        <RegisteringChild value={metadata('sb_two')} />
        <MetadataReader />
      </CapabilityWorkbenchInfoProvider>,
    );

    await screen.findByText('sb_two');

    rerender(
      <CapabilityWorkbenchInfoProvider>
        <RegisteringChild value={null} />
        <MetadataReader />
      </CapabilityWorkbenchInfoProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('active-metadata')).toHaveTextContent('none');
    });
  });
});
