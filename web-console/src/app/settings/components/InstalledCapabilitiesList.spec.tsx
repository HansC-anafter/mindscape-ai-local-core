import '@testing-library/jest-dom/vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  InstalledCapabilitiesList,
  hasBackendProcessRestartRequired,
} from './InstalledCapabilitiesList';
import type { CapabilityPack } from '../types';

function pack(overrides: Partial<CapabilityPack> = {}): CapabilityPack {
  return {
    id: 'ig',
    name: 'Instagram',
    description: 'Instagram pack',
    ai_members: [],
    capabilities: [],
    playbooks: [],
    required_tools: [],
    installed: true,
    version: '1.0.0',
    activation: {
      pack_id: 'ig',
      pack_family: 'capability_api',
      enabled: true,
      install_state: 'installed',
      migration_state: 'applied',
      activation_state: 'active',
      activation_mode: 'capability_registry_load',
      embedding_state: 'indexed',
      registered_prefixes: [],
    },
    ...overrides,
  };
}

describe('InstalledCapabilitiesList restart badge', () => {
  it('does not show pending restart for an active pack without process restart requirement', () => {
    render(
      <InstalledCapabilitiesList
        packs={[
          pack({
            activation: {
              ...pack().activation!,
              activation_state: 'pending_restart',
              backend_process_restart_required: false,
            },
          }),
        ]}
      />,
    );

    expect(screen.queryByText('pending restart')).not.toBeInTheDocument();
  });

  it('shows pending restart only when backend process restart is required', () => {
    const target = pack({ backend_process_restart_required: true });

    expect(hasBackendProcessRestartRequired(target)).toBe(true);
    render(<InstalledCapabilitiesList packs={[target]} />);

    expect(screen.getByText('pending restart')).toBeInTheDocument();
  });
});
