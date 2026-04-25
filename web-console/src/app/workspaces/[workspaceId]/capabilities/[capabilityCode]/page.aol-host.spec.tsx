import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import CapabilityPage from './page';

const mockBack = vi.fn();
const mockReplace = vi.fn();
const mockLoadCapabilityUIComponent = vi.fn();

let mockSearchParams = new URLSearchParams();
let mockCapabilityCode = 'ig';

vi.mock('next/navigation', () => ({
  useParams: () => ({
    workspaceId: 'ws-test',
    capabilityCode: mockCapabilityCode,
  }),
  usePathname: () => `/workspaces/ws-test/capabilities/${mockCapabilityCode}`,
  useRouter: () => ({
    back: mockBack,
    replace: mockReplace,
  }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/capability-ui-loader', () => ({
  loadCapabilityUIComponent: (...args: any[]) => mockLoadCapabilityUIComponent(...args),
}));

describe('CapabilityPage AOL host shell', () => {
  beforeEach(() => {
    mockBack.mockReset();
    mockReplace.mockReset();
    mockLoadCapabilityUIComponent.mockReset();
    mockSearchParams = new URLSearchParams();
    mockCapabilityCode = 'ig';

    mockLoadCapabilityUIComponent.mockImplementation(async (_capabilityId: string, componentCode: string) => {
      if (componentCode === 'IGWorkbenchPage') {
        return ({ aolHost }: any) => (
          <button
            type="button"
            onClick={() => {
              void aolHost.onSelectObject({
                ownerPack: 'ig',
                objectKind: 'reference',
                objectId: 'ref_123',
                sourceSurface: 'ig.references_grid',
                elementId: 'ref-card-ref_123',
                label: '@demo_handle #Cq_demo',
                role: 'source',
              });
            }}
          >
            open-object
          </button>
        );
      }
      return null;
    });

    global.fetch = vi.fn().mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === 'http://api.test/api/v1/capability-packs/installed-capabilities') {
        return {
          ok: true,
          json: async () => ([
            {
              id: 'ig',
              code: 'ig',
              display_name: 'Instagram Workbench',
            },
          ]),
        } as Response;
      }

      if (url === 'http://api.test/api/v1/capability-packs/installed-capabilities/ig/ui-components') {
        return {
          ok: true,
          json: async () => ([
            {
              code: 'IGWorkbenchPage',
              path: 'ui/IGWorkbench.tsx',
              description: 'IG workbench',
              export: 'default',
              artifact_types: [],
              playbook_codes: [],
              import_path: '@/app/capabilities/ig/components/IGWorkbenchPage',
            },
          ]),
        } as Response;
      }

      if (url === 'http://api.test/api/v1/workspaces/ws-test/selection/resolve') {
        const payload = JSON.parse(String(options?.body || '{}'));
        expect(payload.hints).toMatchObject({
          owner_pack: 'ig',
          object_kind: 'reference',
          object_id: 'ref_123',
          source_surface: 'ig.references_grid',
        });
        expect(payload.surface).toMatchObject({
          pack_code: 'ig',
          surface_id: 'capability_page:ig:IGWorkbenchPage',
        });

        return {
          ok: true,
          text: async () => JSON.stringify({
            workspace_id: 'ws-test',
            selection_id: payload.selection_id,
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: 'mindscape://ig/reference/ref_123',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_123',
                  workspace_id: 'ws-test',
                  source_surface: 'ig.references_grid',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://ig/reference/ref_123',
                    owner_pack: 'ig',
                    object_kind: 'reference',
                    object_id: 'ref_123',
                    workspace_id: 'ws-test',
                    source_surface: 'ig.references_grid',
                  },
                  title: 'Demo Reference',
                  subtitle: '@demo_handle',
                  summary_text: 'A reference ready for contextual AOL actions.',
                  labels: ['reference', 'ig'],
                  owner_surface_url: '/workspaces/ws-test/capabilities/ig?component=IGWorkbenchPage',
                },
                actions: [
                  {
                    action_code: 'attach_to_meeting',
                    label: 'Bring Into Meeting',
                    description: 'Attach this object to a meeting as a source or target.',
                    verb: 'attach',
                    mode: 'meeting',
                    requires_review: false,
                    target_kind: null,
                  },
                ],
              },
            ],
            candidate_objects: [],
            errors: [],
          }),
        } as Response;
      }

      if (url === 'http://api.test/api/v1/workspaces/ws-test/object-meeting-attach') {
        const payload = JSON.parse(String(options?.body || '{}'));
        expect(payload).toMatchObject({
          meeting_type: 'direction',
          entries: [
            {
              role: 'source',
              ref: {
                owner_pack: 'ig',
                object_kind: 'reference',
                object_id: 'ref_123',
              },
            },
          ],
        });

        return {
          ok: true,
          text: async () => JSON.stringify({
            workspace_id: 'ws-test',
            meeting_id: 'mtg_123',
            status: 'attached',
            attachments: [
              {
                role: 'source',
                ref: {
                  uri: 'mindscape://ig/reference/ref_123',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_123',
                },
                projection_level: 'meeting',
              },
            ],
            target_ref: null,
            staged_refs: [],
            review_routes: ['/review/demo'],
            errors: [],
          }),
        } as Response;
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    }) as any;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('resolves an addressable selection and attaches it to a meeting from the host shell', async () => {
    render(<CapabilityPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'open-object' }));

    expect(await screen.findByTestId('aol-host-panel')).not.toBeNull();
    expect(await screen.findByText('Demo Reference')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Bring Into Meeting' }));

    expect(await screen.findByText(/Meeting ID:/)).not.toBeNull();
    expect(screen.getByText('mtg_123')).not.toBeNull();
    expect(screen.getByText('Review route: /review/demo')).not.toBeNull();
  });
});
