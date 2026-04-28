import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

const mockBack = vi.fn();
const mockReplace = vi.fn();
const mockPush = vi.fn();

let mockSearchParams = new URLSearchParams();
let mockCapabilityCode = 'demo_render_proof';

vi.mock('next/navigation', () => ({
  useParams: () => ({
    workspaceId: 'ws-render-proof',
    capabilityCode: mockCapabilityCode,
  }),
  usePathname: () => `/workspaces/ws-render-proof/capabilities/${mockCapabilityCode}`,
  useRouter: () => ({
    back: mockBack,
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/components/WorkspaceChat', () => ({
  default: function MockWorkspaceChat({
    threadId,
    layoutVariant,
  }: {
    threadId?: string | null;
    layoutVariant?: string;
  }) {
    return (
      <div data-testid="aol-meeting-chat">
        Meeting chat thread: {threadId || 'none'} | layout: {layoutVariant || 'default'}
      </div>
    );
  },
}));

interface CapabilityComponentsContext {
  (key: string): Record<string, unknown>;
  keys: () => string[];
  resolve?: (request: string) => string;
  id?: string;
}

declare global {
  // eslint-disable-next-line no-var
  var __MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__: CapabilityComponentsContext | undefined;
}

function createCapabilityComponentsTestContext(
  modules: Record<string, Record<string, unknown>>,
): CapabilityComponentsContext {
  const context = ((key: string) => {
    const module = modules[key];
    if (!module) {
      throw new Error(`Unknown capability UI test module: ${key}`);
    }
    return module;
  }) as CapabilityComponentsContext;
  context.keys = () => Object.keys(modules);
  context.resolve = (request: string) => request;
  context.id = 'capability-ui-render-proof-test-context';
  return context;
}

describe('CapabilityPage installed render-proof gate', () => {
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    mockBack.mockReset();
    mockPush.mockReset();
    mockReplace.mockReset();
    mockSearchParams = new URLSearchParams();
    mockCapabilityCode = 'demo_render_proof';

    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const renderProofModule = await import('@/test/mocks/capabilityRenderProofPage');
    const testContext = createCapabilityComponentsTestContext({
      './demo_render_proof/components/DemoRenderProofPage.tsx': {
        default: renderProofModule.default,
      },
    });
    globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__ = testContext;

    global.fetch = vi.fn().mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === 'http://api.test/api/v1/capability-packs/installed-capabilities') {
        return {
          ok: true,
          json: async () => ([
            {
              id: 'demo_render_proof',
              code: 'demo_render_proof',
              display_name: 'Demo Render Proof',
            },
          ]),
        } as Response;
      }

      if (url === 'http://api.test/api/v1/capability-packs/installed-capabilities/demo_render_proof/ui-components') {
        return {
          ok: true,
          json: async () => ([
            {
              code: 'DemoRenderProofPage',
              path: 'ui/components/DemoRenderProofPage.tsx',
              description: 'Render proof test component',
              export: 'default',
              artifact_types: [],
              playbook_codes: [],
              import_path: '/app/src/app/capabilities/demo_render_proof/components/DemoRenderProofPage.tsx',
            },
          ]),
        } as Response;
      }

      if (url === 'http://api.test/api/v1/workspaces/ws-render-proof/selection/resolve') {
        const payload = JSON.parse(String(options?.body || '{}'));
        expect(payload.surface).toMatchObject({
          pack_code: 'demo_render_proof',
          surface_id: 'capability_page:demo_render_proof:DemoRenderProofPage',
        });
        expect(payload.hints).toMatchObject({
          owner_pack: 'demo_render_proof',
          object_kind: 'reference',
          object_id: 'demo-ref-1',
          source_surface: 'demo_render_proof.capability_page',
        });

        return {
          ok: true,
          text: async () => JSON.stringify({
            workspace_id: 'ws-render-proof',
            selection_id: payload.selection_id,
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: 'mindscape://demo_render_proof/reference/demo-ref-1',
                  owner_pack: 'demo_render_proof',
                  object_kind: 'reference',
                  object_id: 'demo-ref-1',
                  workspace_id: 'ws-render-proof',
                  source_surface: 'demo_render_proof.capability_page',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://demo_render_proof/reference/demo-ref-1',
                    owner_pack: 'demo_render_proof',
                    object_kind: 'reference',
                    object_id: 'demo-ref-1',
                    workspace_id: 'ws-render-proof',
                    source_surface: 'demo_render_proof.capability_page',
                  },
                  title: 'Render Proof Object',
                  subtitle: 'demo_render_proof',
                  summary_text: 'A loader-backed capability page selection.',
                  labels: ['render-proof', 'capability-page'],
                  owner_surface_url: '/workspaces/ws-render-proof/capabilities/demo_render_proof',
                },
                actions: [
                  {
                    action_code: 'attach_to_meeting',
                    label: 'Bring Into Meeting',
                    description: 'Attach this object to a meeting.',
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

      if (url === 'http://api.test/api/v1/workspaces/ws-render-proof/object-meeting-attach') {
        const payload = JSON.parse(String(options?.body || '{}'));
        expect(payload).toMatchObject({
          meeting_type: 'direction',
          entries: [
            {
              role: 'source',
              ref: {
                owner_pack: 'demo_render_proof',
                object_kind: 'reference',
                object_id: 'demo-ref-1',
              },
            },
          ],
        });

        return {
          ok: true,
          text: async () => JSON.stringify({
            workspace_id: 'ws-render-proof',
            meeting_id: 'mtg_render_proof',
            status: 'attached',
            attachments: [
              {
                role: 'source',
                ref: {
                  uri: 'mindscape://demo_render_proof/reference/demo-ref-1',
                  owner_pack: 'demo_render_proof',
                  object_kind: 'reference',
                  object_id: 'demo-ref-1',
                },
                projection_level: 'meeting',
              },
            ],
            target_ref: null,
            staged_refs: [],
            review_routes: ['/review/render-proof'],
            errors: [],
          }),
        } as Response;
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    }) as any;
  });

  afterEach(() => {
    delete globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__;
    vi.clearAllMocks();
  });

  it('loads the installed capability page through the real loader and processes an AOL selection callback', async () => {
    vi.resetModules();
    const { default: CapabilityPage } = await import('./page');

    render(<CapabilityPage />);

    expect(await screen.findByTestId('aol-global-anchor')).not.toBeNull();

    expect(await screen.findByTestId('render-proof-component')).not.toBeNull();
    expect(screen.queryByText(/No UI components available/)).toBeNull();
    expect(screen.queryByText('Component failed to render')).toBeNull();

    fireEvent.click(screen.getByTestId('aol-global-anchor'));
    expect(await screen.findByText('Select an object on this page')).not.toBeNull();

    fireEvent.click(screen.getByTestId('render-proof-object-card'));

    const panel = await screen.findByTestId('aol-host-panel');
    expect(panel).not.toBeNull();
    expect(within(panel).getAllByText('Render Proof Object')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Open Meeting' }));

    expect(await screen.findByTestId('aol-meeting-pane')).not.toBeNull();
    expect(await screen.findByTestId('aol-meeting-bottom-shell')).not.toBeNull();
    expect(screen.queryByTestId('aol-host-panel')).toBeNull();
    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    const objectContextPanel = await screen.findByTestId('meeting-object-context-panel');
    expect(within(objectContextPanel).getByText('Render Proof Object')).not.toBeNull();
    expect(within(objectContextPanel).getByText('mtg_render_proof')).not.toBeNull();
    expect(mockPush).not.toHaveBeenCalled();

    const warningMessages = consoleWarnSpy.mock.calls
      .map((call) => call.map((value) => String(value)).join(' '));
    const errorMessages = consoleErrorSpy.mock.calls
      .map((call) => call.map((value) => String(value)).join(' '));

    expect(
      warningMessages.some((message) =>
        message.includes('Context key not found in bundle') ||
        message.includes('UI component DemoRenderProofPage not found') ||
        message.includes('Capability demo_render_proof UI components not available') ||
        message.includes('Failed to import UI component'),
      ),
    ).toBe(false);
    expect(
      errorMessages.some((message) =>
        message.includes('[CapabilityPage] Error in component') ||
        message.includes('[loadCapabilityUIComponent] Failed to import UI component'),
      ),
    ).toBe(false);
  });
});
