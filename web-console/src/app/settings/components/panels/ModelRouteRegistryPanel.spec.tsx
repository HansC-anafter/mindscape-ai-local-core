import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { ModelRouteRegistryPanel } from './ModelRouteRegistryPanel';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('../../../../lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

describe('ModelRouteRegistryPanel', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === 'http://api.test/api/v1/settings/model-route-registry') {
        return new Response(
          JSON.stringify({
            summary: {
              total_slot_count: 1,
              local_core_slot_count: 1,
              installed_pack_count_scanned: 0,
              installed_pack_count_with_slots: 0,
              installed_pack_slot_count: 0,
              registered_runtime_count: 0,
              registered_runtime_slot_count: 0,
              packs_with_registration_drift: [],
            },
            local_core_slots: [],
            pack_groups: [],
            pack_coverage: [],
            registered_runtimes: [],
            policy: {
              route_authority: 'model-routing-registry',
              precedence: [
                {
                  key: 'global_registry',
                  label: 'Global registry default',
                  summary: 'Global registry is authoritative.',
                  active: true,
                },
                {
                  key: 'workspace_override',
                  label: 'Workspace override',
                  summary: 'Workspace override is disabled.',
                  active: false,
                },
              ],
              workspace_override: {
                enabled: false,
                summary: 'Workspace override is disabled.',
              },
              fallback_policy: {
                allowed: false,
                mode: 'fail_closed',
                summary: 'Fallback is disallowed by default.',
              },
            },
            executor_policy: {
              route_authority: 'model-routing-registry',
              precedence: [
                {
                  key: 'workspace_executor_override',
                  label: 'Workspace Executor Override',
                  summary: 'Workspace executor override is authoritative.',
                  active: true,
                },
                {
                  key: 'workspace_surface_binding',
                  label: 'Workspace Surface Runtime Binding',
                  summary: 'Workspace surface runtime binding is active.',
                  active: true,
                },
              ],
              workspace_override: {
                enabled: true,
                summary: 'Workspace executor runtime is pinned to codex_cli.',
              },
              fallback_policy: {
                allowed: false,
                mode: 'fail_closed',
                summary: 'Runtime substitution is disabled by default.',
              },
            },
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      }

      return new Response(JSON.stringify({ detail: `Unhandled fetch ${url}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('renders model and executor routing authority with fail-closed policy', async () => {
    render(<ModelRouteRegistryPanel />);

    await waitFor(() => {
      expect(screen.getByText('Routing Policy')).toBeInTheDocument();
    });

    expect(screen.getAllByText('model-routing-registry')).toHaveLength(2);
    expect(screen.getByText('Global registry default')).toBeInTheDocument();
    expect(screen.getAllByText('Workspace override')).toHaveLength(3);
    expect(screen.getAllByText('fail_closed')).toHaveLength(2);
    expect(screen.getByText(/fallback disallowed/i)).toBeInTheDocument();
    expect(screen.getByText('Executor Runtime Policy')).toBeInTheDocument();
    expect(screen.getByText('Workspace Executor Override')).toBeInTheDocument();
    expect(screen.getByText(/runtime substitution disallowed/i)).toBeInTheDocument();
  });
});
