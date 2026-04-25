import '@testing-library/jest-dom/vitest';
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PerformanceDirectionStoryboardEditorPage from './PerformanceDirectionStoryboardEditorPage';

const useSearchParamsMock = vi.fn();
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => useSearchParamsMock(),
  useRouter: () => ({
    push: mockPush,
  }),
}));

function okJson(payload: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(JSON.stringify(payload)),
  });
}

function buildSubject({
  subjectId,
  roleId,
  sourceReferenceIds,
}: {
  subjectId: string;
  roleId: string;
  sourceReferenceIds?: string[];
}) {
  return {
    subject_id: subjectId,
    role_id: roleId,
    source_reference_ids: sourceReferenceIds || [`ref_${subjectId}`],
    locators: [],
    provenance: {},
  };
}

function buildSlot({
  slotId,
  slotRole,
  scopeKind = 'subject',
  subjectId = '',
  packageRefs = [],
}: {
  slotId: string;
  slotRole: string;
  scopeKind?: string;
  subjectId?: string;
  packageRefs?: Array<Record<string, unknown>>;
}) {
  return {
    slot_id: slotId,
    slot_role: slotRole,
    scope_kind: scopeKind,
    subject_id: subjectId,
    binding_mode: 'adapter_only',
    package_refs: packageRefs,
  };
}

function buildScene({
  sceneId,
  summary,
  durationSec = 6,
  referenceIds,
  subjects,
  slots,
  extras,
}: {
  sceneId: string;
  summary: string;
  durationSec?: number;
  referenceIds?: string[];
  subjects?: Array<Record<string, unknown>>;
  slots?: Array<Record<string, unknown>>;
  extras?: Record<string, unknown>;
}) {
  return {
    scene_id: sceneId,
    duration_sec: durationSec,
    reference_ids: referenceIds || [`ref_${sceneId}`],
    intent: { summary },
    direction_ir: {
      scene_subjects: subjects || [],
      character_adapter_slots: slots || [],
    },
    ...(extras || {}),
  };
}

function buildStoryboardPayload(
  scenes: Array<Record<string, unknown>>,
  extras?: Record<string, unknown>,
) {
  return {
    success: true,
    artifact: {
      artifact_id: String(extras?.artifact_id || 'da_storyboard_1'),
    },
    storyboard: {
      workspace_id: 'ws_demo',
      scenes,
    },
    ...(extras || {}),
  };
}

const PACKAGE_RECORD = {
  package_id: 'ctp_face_ava_v1',
  default_display_name: 'Ava Face Anchor',
  status: 'published',
  package_kind: 'identity',
  identity_scope: 'face_identity',
  identity_domain: 'clean_sfw_base',
  supported_families: ['sdxl'],
  recommended_use_modes: ['adapter_only'],
  render_binding_presets: [
    {
      preset_id: 'sdxl_hybrid_v1',
      binding_mode: 'adapter_only',
      model_family: 'sdxl',
    },
  ],
  artifact_links: [
    {
      role_in_package: 'primary_adapter',
      artifact_id: 'cta_ava_face_anchor',
    },
  ],
};

const RESOLVED_PACKAGE = {
  package_id: 'ctp_face_ava_v1',
  selected_preset_id: 'sdxl_hybrid_v1',
  resolution_status: 'ready',
  character_binding_mode: 'adapter_only',
  identity_scope: 'face_identity',
  identity_domain: 'clean_sfw_base',
  character_adapter_refs: [
    {
      adapter_type: 'lora',
      model_id: 'ava_face_anchor_v1',
      artifact_id: 'cta_ava_face_anchor',
    },
  ],
  character_bindings: [
    {
      role_id: 'lead_model',
      asset_ref: { reference_id: 'ref_subject_a' },
    },
  ],
  runtime_capability_requirements: ['character_lora_loader'],
};

type FetchMockOptions = {
  storyboardResponses?: unknown[];
  recentSessionsResponse?: unknown;
  createSessionResponse?: unknown;
  packagesResponse?: unknown;
  resolvedPackageResponse?: unknown;
  proposalReviewResponse?: unknown;
  reorderScenesResponse?: unknown;
  sceneActionsResponse?: unknown;
  scenePatchResponse?: unknown;
  applyStoryboardScenePatchResponse?: unknown;
  executeStoryboardResponse?: unknown;
  runStatusResponse?: unknown;
};

function installFetchMock({
  storyboardResponses,
  recentSessionsResponse,
  createSessionResponse,
  packagesResponse,
  resolvedPackageResponse,
  proposalReviewResponse,
  reorderScenesResponse,
  sceneActionsResponse,
  scenePatchResponse,
  applyStoryboardScenePatchResponse,
  executeStoryboardResponse,
  runStatusResponse,
}: FetchMockOptions = {}) {
  let storyboardLoadCount = 0;
  const storyboardPayloads = storyboardResponses || [];
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/sessions?')) {
      return okJson(
        recentSessionsResponse || {
          success: true,
          sessions: [],
        },
      );
    }
    if (url.endsWith('/sessions') && String(init?.method || 'GET').toUpperCase() === 'POST') {
      return okJson(
        createSessionResponse || {
          success: true,
          session: {
            session_id: 'ds_created_001',
            workspace_id: 'ws_demo',
            status: 'draft',
            reference_ids: [],
          },
        },
      );
    }
    if (url.includes('/storyboard/proposals/')) {
      return okJson(
        proposalReviewResponse || {
          success: true,
          artifact: { artifact_id: 'da_storyboard_reviewed_1' },
        },
      );
    }
    if (url.includes('/storyboard/reorder-scenes')) {
      return okJson(
        reorderScenesResponse || {
          success: true,
          artifact: { artifact_id: 'da_storyboard_2' },
          reordered_scene_ids: ['sc02', 'sc01'],
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [{ scene_id: 'sc02' }, { scene_id: 'sc01' }],
          },
        },
      );
    }
    if (url.includes('/storyboard/scene-actions')) {
      return okJson(
        sceneActionsResponse || {
          success: true,
          action: 'duplicate_scene',
          artifact: { artifact_id: 'da_storyboard_2' },
          selected_scene_id: 'sc01_copy',
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [{ scene_id: 'sc01' }, { scene_id: 'sc01_copy' }],
          },
        },
      );
    }
    if (url.includes('/storyboard') && !url.includes('/scene-patch')) {
      const payload =
        storyboardPayloads[Math.min(storyboardLoadCount, Math.max(storyboardPayloads.length - 1, 0))] ||
        buildStoryboardPayload([]);
      storyboardLoadCount += 1;
      return okJson(payload);
    }
    if (url.includes('/character_training/packages/') && url.includes('/resolved')) {
      return okJson(
        resolvedPackageResponse || {
          success: true,
          package: RESOLVED_PACKAGE,
        },
      );
    }
    if (url.includes('/character_training/packages')) {
      return okJson(
        packagesResponse || {
          success: true,
          packages: [],
        },
      );
    }
    if (url.includes('/apply-storyboard-scene-patch')) {
      return okJson(
        applyStoryboardScenePatchResponse || {
          success: true,
          patched_scene_id: 'sc01',
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [{ scene_id: 'sc01' }],
          },
        },
      );
    }
    if (url.includes('/execute-storyboard')) {
      return okJson(
        executeStoryboardResponse || {
          success: true,
          run: { run_id: 'run_preview_1' },
          run_status_endpoint: '/api/v1/capabilities/multi_media_studio/production-runs/run_preview_1',
          run_summary: {
            status: 'queued',
            scene_status_counts: { queued: 1 },
            active_scene_ids: ['sc01'],
            active_prompt_ids: ['prompt_preview_1'],
            has_pending_work: true,
            recommended_poll_seconds: 2,
          },
        },
      );
    }
    if (url.includes('/production-runs/run_preview_1')) {
      return okJson(
        runStatusResponse || {
          run: { run_id: 'run_preview_1', status: 'completed' },
          run_status_endpoint: '/api/v1/capabilities/multi_media_studio/production-runs/run_preview_1',
          run_summary: {
            status: 'completed',
            scene_status_counts: { completed: 1 },
            active_scene_ids: [],
            active_prompt_ids: [],
            has_pending_work: false,
            recommended_poll_seconds: null,
          },
        },
      );
    }
    if (url.includes('/storyboard/scene-patch')) {
      return okJson(
        scenePatchResponse || {
          success: true,
          patched_scene_id: 'sc01',
          artifact: { artifact_id: 'da_storyboard_2' },
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [{ scene_id: 'sc01' }],
          },
        },
      );
    }
    return okJson({ success: true });
  });

  global.fetch = fetchMock as any;
  return fetchMock;
}

function renderWithSession(
  storyboardResponses: unknown[],
  fetchOptions?: Omit<FetchMockOptions, 'storyboardResponses'>,
) {
  useSearchParamsMock.mockReturnValue(new URLSearchParams('sessionId=ds_demo_001'));
  const fetchMock = installFetchMock({
    storyboardResponses,
    ...(fetchOptions || {}),
  });
  render(<PerformanceDirectionStoryboardEditorPage workspaceId="ws_demo" />);
  return fetchMock;
}

async function waitForInitialStoryboardLoad(fetchMock: ReturnType<typeof installFetchMock>) {
  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });
  await screen.findByText('Story Sequence Board');
}

async function openCastPerformanceTab() {
  fireEvent.click(screen.getByRole('button', { name: /Cast \/ Performance/i }));
  await screen.findByText('Material anchors and person mapping');
}

async function openContinuityEditorialTab() {
  fireEvent.click(screen.getByRole('button', { name: /Continuity \/ Editorial/i }));
  await screen.findByText('Coverage and continuity guardrail');
}

async function openAiRuntimeTab() {
  fireEvent.click(screen.getByRole('button', { name: /AI \/ Runtime/i }));
  await screen.findByText('Face / body / style binding lanes');
}

describe('PerformanceDirectionStoryboardEditorPage', () => {
  beforeEach(() => {
    useSearchParamsMock.mockReturnValue(new URLSearchParams());
    global.fetch = vi.fn();
    window.localStorage.clear();
    mockPush.mockReset();
  });

  it('renders the PD start surface before a storyboard is loaded', async () => {
    installFetchMock({
      recentSessionsResponse: {
        success: true,
        sessions: [
          {
            session_id: 'ds_recent_001',
            display_label: 'Editorial loft open',
            intent_summary: 'Lock the editorial loft opening beat.',
            status: 'draft',
            scene_count: 3,
            reference_ids_count: 2,
            pending_proposal_count: 1,
            updated_at: '2026-04-21T18:30:00+08:00',
            has_storyboard: true,
          },
        ],
      },
    });

    render(<PerformanceDirectionStoryboardEditorPage workspaceId="ws_demo" />);

    expect(await screen.findByText('PD Start Surface')).toBeInTheDocument();
    expect(screen.getByText('Start New Direction Session')).toBeInTheDocument();
    expect(screen.getByText('Resume Recent Session')).toBeInTheDocument();
    expect(screen.getByText('Editorial loft open')).toBeInTheDocument();
    expect(screen.getByText('Advanced / Ops')).toBeInTheDocument();
  });

  it('creates a new direction session from the start surface', async () => {
    const fetchMock = installFetchMock({
      recentSessionsResponse: {
        success: true,
        sessions: [],
      },
      createSessionResponse: {
        success: true,
        session: {
          session_id: 'ds_created_123',
          workspace_id: 'ws_demo',
          status: 'draft',
          reference_ids: ['ref_a', 'ref_b'],
        },
      },
    });

    render(<PerformanceDirectionStoryboardEditorPage workspaceId="ws_demo" />);

    await screen.findByText('PD Start Surface');
    fireEvent.change(screen.getByLabelText('這次要導什麼？'), {
      target: { value: 'Lock the cold open reveal.' },
    });
    fireEvent.change(screen.getByLabelText('要帶進來的參考素材 ID（選填，可逗號或換行分隔）'), {
      target: { value: 'ref_a, ref_b' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Create direction session/i }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith('/sessions') &&
          String((init as RequestInit | undefined)?.method || '').toUpperCase() === 'POST',
      );
      expect(createCall).toBeTruthy();
      expect(JSON.parse(String((createCall?.[1] as RequestInit)?.body || '{}'))).toMatchObject({
        workspace_id: 'ws_demo',
        intent: { summary: 'Lock the cold open reveal.' },
        reference_ids: ['ref_a', 'ref_b'],
      });
    });

    expect(await screen.findByText(/Created ds_created_123/i)).toBeInTheDocument();
  });

  it('navigates to a session-bound route when launcher mode creates a session', async () => {
    installFetchMock({
      recentSessionsResponse: {
        success: true,
        sessions: [],
      },
      createSessionResponse: {
        success: true,
        session: {
          session_id: 'ds_created_route_001',
          workspace_id: 'ws_demo',
          status: 'draft',
          reference_ids: [],
        },
      },
    });

    render(
      <PerformanceDirectionStoryboardEditorPage
        workspaceId="ws_demo"
        routeMode="launcher"
        sessionRouteBasePath="/workspaces/ws_demo/capabilities/performance_direction/sessions"
      />,
    );

    await screen.findByText('PD Start Surface');
    fireEvent.change(screen.getByLabelText('這次要導什麼？'), {
      target: { value: 'Route split smoke.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Create direction session/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        '/workspaces/ws_demo/capabilities/performance_direction/sessions/ds_created_route_001',
      );
    });
    expect(screen.queryByText(/Created ds_created_route_001/i)).toBeNull();
  });

  it('resumes a recent session from the start surface', async () => {
    const fetchMock = installFetchMock({
      recentSessionsResponse: {
        success: true,
        sessions: [
          {
            session_id: 'ds_recent_002',
            display_label: 'Resume loft cut',
            intent_summary: 'Continue the approved loft cut.',
            status: 'active',
            scene_count: 2,
            reference_ids_count: 1,
            pending_proposal_count: 0,
            updated_at: '2026-04-21T18:30:00+08:00',
            has_storyboard: true,
          },
        ],
      },
      storyboardResponses: [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          }),
        ]),
      ],
    });

    render(<PerformanceDirectionStoryboardEditorPage workspaceId="ws_demo" />);

    fireEvent.click(await screen.findByRole('button', { name: /Resume loft cut/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/capabilities/performance_direction/sessions/ds_recent_002/storyboard',
        expect.objectContaining({ credentials: 'same-origin' }),
      );
    });
    expect(await screen.findByText('Story Sequence Board')).toBeInTheDocument();
  });

  it('shows IG continuation context when local storage contains a PD handoff', async () => {
    window.localStorage.setItem('ig.references.scene_preview.pd_session:ws_demo', 'ds_ig_001');
    window.localStorage.setItem('ig.references.scene_preview.project:ws_demo', 'proj_demo');
    window.localStorage.setItem('ig.references.scene_preview.scope:ws_demo', 'reference_detail');
    window.localStorage.setItem('ig.references.scene_preview.variant:ws_demo', 'hero');
    installFetchMock({
      recentSessionsResponse: {
        success: true,
        sessions: [],
      },
    });

    render(<PerformanceDirectionStoryboardEditorPage workspaceId="ws_demo" />);

    expect(await screen.findByText('Continue IG Scene Preview Session')).toBeInTheDocument();
    expect(screen.getByText(/Project proj_demo/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Resume in PD/i })).toBeInTheDocument();
  });

  it('keeps launcher sections out of the session-bound workbench route', async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/sessions?')) {
        return okJson({ success: true, sessions: [] });
      }
      if (url.includes('/sessions/ds_route_001/storyboard')) {
        return {
          ok: false,
          status: 404,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ detail: 'storyboard_not_found' }),
          text: async () => JSON.stringify({ detail: 'storyboard_not_found' }),
        } as Response;
      }
      return okJson({ success: true });
    }) as any;

    render(
      <PerformanceDirectionStoryboardEditorPage
        workspaceId="ws_demo"
        routeMode="workbench"
        routeSessionId="ds_route_001"
      />,
    );

    expect(await screen.findByText('Direction session ID')).not.toBeNull();
    expect(screen.queryByText('PD Start Surface')).toBeNull();
    expect(screen.queryByText('Start New Direction Session')).toBeNull();
    expect(await screen.findByTestId('pd-session-workbench-empty-state')).not.toBeNull();
    expect(screen.queryByText('storyboard_not_found')).toBeNull();
  });

  it('loads storyboard scenes and seeds subject and slot editors from query session id', async () => {
    const fetchMock = renderWithSession(
      [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            referenceIds: ['ref_scene_a'],
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model', sourceReferenceIds: ['ref_subject_a'] })],
            slots: [
              buildSlot({
                slotId: 'subj_a_face',
                slotRole: 'identity_face',
                subjectId: 'subj_a',
                packageRefs: [{ package_id: 'char.face_anchor.v1' }],
              }),
            ],
          }),
        ]),
      ],
      {
        packagesResponse: {
          success: true,
          packages: [PACKAGE_RECORD],
        },
        resolvedPackageResponse: {
          success: true,
          package: RESOLVED_PACKAGE,
        },
      },
    );

    await waitForInitialStoryboardLoad(fetchMock);

    expect(screen.getByText('Sequence / scene / shot orchestration')).toBeInTheDocument();
    expect(screen.getByText('Storyboard sheet / sequence / previs handoff')).toBeInTheDocument();
    expect(screen.getAllByText('Director Desk').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Story Timeline').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Department Workspace').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Run preview for this scene/i })).toBeInTheDocument();

    await openCastPerformanceTab();
    expect(screen.getByDisplayValue('subj_a')).toBeInTheDocument();
    expect(screen.getByDisplayValue('lead_model')).toBeInTheDocument();

    await openAiRuntimeTab();
    expect(screen.getByDisplayValue('subj_a_face')).toBeInTheDocument();
    expect(screen.getByLabelText('slot_role')).toHaveValue('identity_face');
    expect(
      (screen.getByLabelText('package_refs') as HTMLTextAreaElement).value.includes(
        'char.face_anchor.v1',
      ),
    ).toBe(true);
    expect(screen.getByText('CT package browser')).toBeInTheDocument();
    expect(screen.getByText('Ava Face Anchor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Assign' })).toBeInTheDocument();
    expect(screen.getByText('Presets')).toBeInTheDocument();
    expect(screen.getByText('Artifacts')).toBeInTheDocument();
    expect(screen.getByText('Package resolved view')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/packages/ctp_face_ava_v1/resolved'))).toBe(
        true,
      );
    });
    expect(await screen.findByText('character_lora_loader')).toBeInTheDocument();
  });

  it('surfaces pending proposals and lets PD review them', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload(
        [
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          }),
        ],
        {
          pending_proposals: [
            {
              artifact_id: 'da_storyboard_proposal_1',
              branch_kind: 'proposal',
              proposal_origin: 'mms',
              editorial_status: 'pending_review',
              patched_scene_id: 'sc01',
            },
          ],
        },
      ),
      buildStoryboardPayload(
        [
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          }),
        ],
        {
          artifact_id: 'da_storyboard_accepted_1',
          pending_proposals: [],
        },
      ),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    expect(screen.getByText('Proposal Review Strip')).toBeInTheDocument();
    expect(screen.getByText(/artifact da_storyboard_proposal_1/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).includes('/storyboard/proposals/da_storyboard_proposal_1/review'),
        ),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(screen.queryByText('Proposal Review Strip')).not.toBeInTheDocument();
    });
  });

  it('persists reordered scene order through the canonical storyboard route', async () => {
    const fetchMock = renderWithSession(
      [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          }),
          buildScene({
            sceneId: 'sc02',
            summary: 'Closer detail',
            subjects: [buildSubject({ subjectId: 'subj_b', roleId: 'detail_model' })],
          }),
        ]),
      ],
      {
        reorderScenesResponse: {
          success: true,
          artifact: { artifact_id: 'da_storyboard_2' },
          reordered_scene_ids: ['sc02', 'sc01'],
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [
              buildScene({
                sceneId: 'sc02',
                summary: 'Closer detail',
                subjects: [buildSubject({ subjectId: 'subj_b', roleId: 'detail_model' })],
                extras: {
                  scene_manifest: {
                    sequence_id: 'sequence_01',
                    sequence_label: 'Sequence 1',
                    story_unit_type: 'scene',
                    sequence_index: 0,
                  },
                },
              }),
              buildScene({
                sceneId: 'sc01',
                summary: 'Hero intro',
                subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
                extras: {
                  scene_manifest: {
                    sequence_id: 'sequence_01',
                    sequence_label: 'Sequence 1',
                    story_unit_type: 'scene',
                    sequence_index: 1,
                  },
                },
              }),
            ],
          },
        },
      },
    );

    await waitForInitialStoryboardLoad(fetchMock);

    const storyBoard = screen.getByText('Story Sequence Board').closest('section');
    expect(storyBoard).not.toBeNull();
    const heroCard = within(storyBoard as HTMLElement).getByRole('button', {
      name: /Hero intro/i,
    });
    fireEvent.click(within(heroCard).getByRole('button', { name: 'Move scene right' }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).includes('/storyboard/reorder-scenes'),
        ),
      ).toBe(true);
    });

    const reorderCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/storyboard/reorder-scenes'),
    );
    expect(reorderCall).toBeTruthy();
    expect(JSON.parse(String((reorderCall?.[1] as RequestInit)?.body || '{}'))).toMatchObject({
      scene_ids: ['sc02', 'sc01'],
      artifact_id: 'da_storyboard_1',
    });
  });

  it('dispatches storyboard sheet actions through the canonical scene action route', async () => {
    const fetchMock = renderWithSession(
      [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            durationSec: 6,
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
            extras: {
              scene_manifest: {
                sequence_id: 'sequence_01',
                sequence_label: 'Sequence 1',
                story_unit_type: 'scene',
                scene_reference_image: {
                  url: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="100%" height="100%" fill="%23f5efe6"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="18">Hero Intro</text></svg>',
                  reference_id: 'ref_scene_sc01',
                },
              },
            },
          }),
        ]),
      ],
      {
        sceneActionsResponse: {
          success: true,
          action: 'duplicate_scene',
          artifact: { artifact_id: 'da_storyboard_2' },
          selected_scene_id: 'sc01_copy',
          storyboard: {
            workspace_id: 'ws_demo',
            scenes: [
              buildScene({
                sceneId: 'sc01',
                summary: 'Hero intro',
                durationSec: 6,
                subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
                extras: {
                  scene_manifest: {
                    sequence_id: 'sequence_01',
                    sequence_label: 'Sequence 1',
                    story_unit_type: 'scene',
                  },
                },
              }),
              buildScene({
                sceneId: 'sc01_copy',
                summary: 'Hero intro (copy)',
                durationSec: 6,
                subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
                extras: {
                  scene_manifest: {
                    sequence_id: 'sequence_01',
                    sequence_label: 'Sequence 1',
                    story_unit_type: 'scene',
                  },
                },
              }),
            ],
          },
        },
      },
    );

    await waitForInitialStoryboardLoad(fetchMock);

    fireEvent.click(screen.getByRole('button', { name: 'Duplicate Scene' }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/storyboard/scene-actions')),
      ).toBe(true);
    });

    const sceneActionCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/storyboard/scene-actions'),
    );
    expect(sceneActionCall).toBeTruthy();
    expect(JSON.parse(String((sceneActionCall?.[1] as RequestInit)?.body || '{}'))).toMatchObject({
      action: 'duplicate_scene',
      scene_id: 'sc01',
      artifact_id: 'da_storyboard_1',
    });

    await waitFor(() => {
      expect(screen.getByText('Artifact: da_storyboard_2')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /Hero intro \(copy\)/i }).length).toBeGreaterThan(0);
    });
  });

  it('routes world dock handoff receipts into the production design lane', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          durationSec: 6,
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          extras: {
            scene_manifest: {
              scene_package_artifact_id: 'pkg_scene_sc01',
              scene_reference_image: {
                url: 'https://example.invalid/scene-sc01.png',
                reference_id: 'ref_scene_sc01',
              },
            },
            world_interchange_refs: [
              {
                kind: 'openusd',
                stage_ref: {
                  identifier: 'usd://scene/sc01.usda',
                },
                composition_metadata: {
                  package_id: 'openusd_scene_pkg_sc01',
                },
              },
            ],
          },
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    expect(
      document.querySelector('[data-world-dock-action="openusd_world"]'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'OpenUSD World Handoff' }));

    await waitFor(() => {
      expect(screen.getByText('openusd_world')).toBeInTheDocument();
      expect(screen.getByText('ref_kind: openusd_stage')).toBeInTheDocument();
      expect(screen.getByText('artifact_id: pkg_scene_sc01')).toBeInTheDocument();
      expect(
        document.querySelector(
          '[data-world-dock-receipt="true"][data-destination-pack="openusd_world"][data-ref-kind="openusd_stage"]',
        ),
      ).toBeInTheDocument();
    });
  });

  it('surfaces a human-readable storyboard packet for the selected scene', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero rooftop arrival',
          durationSec: 6,
          subjects: [
            buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' }),
            buildSubject({ subjectId: 'subj_b', roleId: 'support_model' }),
          ],
          slots: [
            buildSlot({
              slotId: 'scene_style_primary',
              slotRole: 'style',
              scopeKind: 'scene',
              packageRefs: [{ package_id: 'wardrobe_city_night_v2' }],
            }),
          ],
          extras: {
            intent: {
              summary: 'Hero rooftop arrival',
              description:
                'Hero lands on the rooftop, reveals the jacket, and sets the chase story line.',
            },
            reference_ids: ['ref_scene_sc01', 'ref_costume_sc01'],
            character_package_refs: [{ package_id: 'character_anchor_lead_v1' }],
            object_assets: [
              {
                object_target_id: 'hero_jacket',
                asset_ref: { storage_key: 'props/hero_jacket.glb' },
              },
              {
                object_target_id: 'neon_sign',
                asset_ref: { storage_key: 'props/neon_sign.glb' },
              },
            ],
            world_interchange_refs: [
              {
                kind: 'openusd',
                stage_ref: { identifier: 'usd://scene/sc01.usda' },
                composition_metadata: { package_id: 'openusd_scene_pkg_sc01' },
              },
            ],
            scene_manifest: {
              sequence_id: 'sequence_01',
              sequence_label: 'Sequence 1',
              story_unit_type: 'scene',
              scene_package_artifact_id: 'pkg_scene_sc01',
            },
          },
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    expect(screen.getByText('Human-readable storyboard sheet')).toBeInTheDocument();

    const humanReadableSheetCard = screen
      .getByText('Human-readable storyboard sheet')
      .closest('div')?.parentElement as HTMLElement | null;

    expect(humanReadableSheetCard).not.toBeNull();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('Story beat')).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('Hero rooftop arrival')).toBeInTheDocument();
    expect(
      within(humanReadableSheetCard as HTMLElement).getByText(
        'Hero lands on the rooftop, reveals the jacket, and sets the chase story line.',
      ),
    ).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('lead_model · subj_a')).toBeInTheDocument();
    expect(
      within(humanReadableSheetCard as HTMLElement).getByText('support_model · subj_b'),
    ).toBeInTheDocument();
    expect(
      within(humanReadableSheetCard as HTMLElement).getByText('wardrobe_city_night_v2'),
    ).toBeInTheDocument();
    expect(
      within(humanReadableSheetCard as HTMLElement).getByText('character_anchor_lead_v1'),
    ).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('hero_jacket')).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('neon_sign')).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('pkg_scene_sc01')).toBeInTheDocument();
    expect(
      within(humanReadableSheetCard as HTMLElement).getByText('openusd_scene_pkg_sc01'),
    ).toBeInTheDocument();
    expect(within(humanReadableSheetCard as HTMLElement).getByText('ref_costume_sc01')).toBeInTheDocument();
  });

  it('preserves per-scene drafts when switching between scenes', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
        }),
        buildScene({
          sceneId: 'sc02',
          summary: 'Closer detail',
          subjects: [buildSubject({ subjectId: 'subj_b', roleId: 'detail_model' })],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openCastPerformanceTab();

    expect(screen.getByDisplayValue('lead_model')).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue('lead_model'), {
      target: { value: 'lead_model_updated' },
    });

    fireEvent.click(screen.getAllByRole('button', { name: /Closer detail/i })[0]);

    await waitFor(() => {
      expect(screen.getByDisplayValue('subj_b')).toBeInTheDocument();
      expect(screen.getByDisplayValue('detail_model')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: /Hero intro/i })[0]);

    await waitFor(() => {
      expect(screen.getByDisplayValue('lead_model_updated')).toBeInTheDocument();
      expect(screen.getAllByText('Draft').length).toBeGreaterThan(0);
    });
  });

  it('resets the active scene draft back to storyboard state', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openCastPerformanceTab();

    fireEvent.change(screen.getByDisplayValue('lead_model'), {
      target: { value: 'lead_model_updated' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Reset scene draft/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('lead_model')).toBeInTheDocument();
    });
    expect(screen.queryByDisplayValue('lead_model_updated')).not.toBeInTheDocument();
  });

  it('focuses subject chips and switches the active slot context', async () => {
    const fetchMock = renderWithSession(
      [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [
              buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' }),
              buildSubject({ subjectId: 'subj_b', roleId: 'support_model' }),
            ],
            slots: [
              buildSlot({ slotId: 'subj_a_face', slotRole: 'identity_face', subjectId: 'subj_a' }),
              buildSlot({ slotId: 'subj_b_face', slotRole: 'identity_face', subjectId: 'subj_b' }),
            ],
          }),
        ]),
      ],
      {
        packagesResponse: {
          success: true,
          packages: [PACKAGE_RECORD],
        },
      },
    );

    await waitForInitialStoryboardLoad(fetchMock);
    await openAiRuntimeTab();

    expect(screen.getByRole('button', { name: /subj_b · support_model/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Assign to subj_a_face' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /subj_b · support_model/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Assign to subj_b_face' })).toBeInTheDocument();
      expect(screen.getAllByText(/focused subject: subj_b/i).length).toBeGreaterThan(0);
    });
  });

  it('adds a missing body slot from the subject card', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          slots: [buildSlot({ slotId: 'subj_a_face', slotRole: 'identity_face', subjectId: 'subj_a' })],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openCastPerformanceTab();

    fireEvent.click(screen.getByRole('button', { name: /Add body slot/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Body ready · subj_a_body_2/i })).toBeInTheDocument();
    });

    await openAiRuntimeTab();
    expect(screen.getByDisplayValue('subj_a_body_2')).toBeInTheDocument();
  });

  it('adds a missing scene style slot from the scene header', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    fireEvent.click(screen.getByRole('button', { name: /Add scene style slot/i }));

    await waitFor(() => {
      expect(screen.getByText(/ready · style_1/i)).toBeInTheDocument();
    });

    await openAiRuntimeTab();
    expect(screen.getByDisplayValue('style_1')).toBeInTheDocument();
    expect(screen.getByLabelText('scope_kind')).toHaveValue('scene');
  });

  it('quick-browses to a subject body slot from the coverage badge', async () => {
    const fetchMock = renderWithSession(
      [
        buildStoryboardPayload([
          buildScene({
            sceneId: 'sc01',
            summary: 'Hero intro',
            subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
            slots: [
              buildSlot({ slotId: 'subj_a_face', slotRole: 'identity_face', subjectId: 'subj_a' }),
              buildSlot({ slotId: 'subj_a_body', slotRole: 'identity_body', subjectId: 'subj_a' }),
            ],
          }),
        ]),
      ],
      {
        packagesResponse: {
          success: true,
          packages: [PACKAGE_RECORD],
        },
      },
    );

    await waitForInitialStoryboardLoad(fetchMock);
    await openCastPerformanceTab();

    fireEvent.click(screen.getByRole('button', { name: /Body ready · subj_a_body/i }));

    await openAiRuntimeTab();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Assign to subj_a_body' })).toBeInTheDocument();
    });
  });

  it('executes storyboard preview and polls run status from the PD editor', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          slots: [
            buildSlot({
              slotId: 'subj_a_face',
              slotRole: 'identity_face',
              subjectId: 'subj_a',
              packageRefs: [{ package_id: 'char.face_anchor.v1' }],
            }),
          ],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    fireEvent.click(screen.getByRole('button', { name: /Execute preview/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/capabilities/multi_media_studio/production-runs/execute-storyboard',
        expect.objectContaining({
          method: 'POST',
          credentials: 'same-origin',
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/run_id: run_preview_1/i)).toBeInTheDocument();
      expect(screen.getAllByText(/status: completed/i).length).toBeGreaterThan(0);
    });
  });

  it('blocks invalid subject-slot contracts before posting a scene patch', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          slots: [
            buildSlot({
              slotId: 'subj_a_face',
              slotRole: 'identity_face',
              subjectId: 'subj_a',
              packageRefs: [{ package_id: 'char.face_anchor.v1' }],
            }),
          ],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openAiRuntimeTab();

    fireEvent.change(screen.getByLabelText('subject_id'), {
      target: { value: 'subj_missing' },
    });

    await waitFor(() => {
      expect(
        screen.getByText('slot subj_a_face 指向不存在的 subject_id：subj_missing'),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Apply patch/i }));

    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/storyboard/scene-patch')),
    ).toBe(false);
  });

  it('normalizes slot scope semantics when the operator switches a slot to style', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model' })],
          slots: [
            buildSlot({
              slotId: 'subj_a_face',
              slotRole: 'identity_face',
              subjectId: 'subj_a',
              packageRefs: [{ package_id: 'char.face_anchor.v1' }],
            }),
          ],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openAiRuntimeTab();

    expect(screen.getByLabelText('slot_role')).toHaveValue('identity_face');
    expect(screen.getByLabelText('scope_kind')).toHaveValue('subject');

    fireEvent.change(screen.getByLabelText('slot_role'), {
      target: { value: 'style' },
    });

    await waitFor(() => {
      expect(screen.getByLabelText('scope_kind')).toHaveValue('scene');
      expect(screen.getByLabelText('subject_id')).toHaveValue('');
    });
  });

  it('surfaces approval guardrails in story timeline and continuity workspace', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [],
          slots: [],
          extras: {
            decision_items: [
              {
                decision_id: 'decision.world_variant',
                title: 'Choose world variant',
                summary: 'Need resolution before preview.',
                status: 'blocked',
              },
            ],
            coverage_completeness: 'partial',
            approval_state: 'approved',
          },
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    await waitFor(() => {
      expect(screen.getByLabelText('director-desk-review-gate')).toBeInTheDocument();
      expect(screen.getAllByText(/approval approved/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/approval gated/i).length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: /Run preview for this scene/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /Execute preview/i })).toBeDisabled();
      expect(
        screen.getAllByText(/Current approval state is contradictory/i).length,
      ).toBeGreaterThan(0);
    });

    await openContinuityEditorialTab();

    fireEvent.change(screen.getByLabelText('continuity-editorial-approval-state'), {
      target: { value: 'needs_review' },
    });

    await waitFor(() => {
      expect(screen.queryByText(/Current approval state is contradictory/i)).not.toBeInTheDocument();
      expect(
        screen.getByText(/Director desk can keep moving. Approval is not in a contradictory state./i),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Run preview for this scene/i })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: /Execute preview/i })).not.toBeDisabled();
    });
  });

  it('persists variant request policy edits in scene patch payload', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          subjects: [],
          slots: [],
          extras: {
            scene_manifest: {
              mms_variant_request_permission: 'allowed',
            },
          },
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);
    await openContinuityEditorialTab();

    fireEvent.change(screen.getByLabelText('continuity-editorial-variant-request-policy'), {
      target: { value: 'requires_pd_review' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Apply patch/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/storyboard/scene-patch')),
      ).toBe(true);
    });

    const scenePatchCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/storyboard/scene-patch'),
    );
    const scenePatchBody = JSON.parse(String(scenePatchCall?.[1]?.body || '{}'));

    expect(
      scenePatchBody.storyboard_scene_patch.scene_manifest.mms_variant_request_permission,
    ).toBe('requires_pd_review');
  });

  it('persists decision ledger comments, resolution notes, and compare candidate edits in scene patch payload', async () => {
    const fetchMock = renderWithSession([
      buildStoryboardPayload([
        buildScene({
          sceneId: 'sc01',
          summary: 'Hero intro',
          referenceIds: ['ref_a'],
          subjects: [buildSubject({ subjectId: 'subj_a', roleId: 'lead_model', sourceReferenceIds: ['ref_subject_a'] })],
        }),
      ]),
    ]);

    await waitForInitialStoryboardLoad(fetchMock);

    expect(screen.getByText(/Decision Ledger/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));

    const compareCandidateLabels = await screen.findAllByLabelText(/compare-candidate-label-/i);
    fireEvent.change(compareCandidateLabels[0], {
      target: { value: 'Hero alt candidate' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Decision items' }));
    fireEvent.click((await screen.findAllByRole('button', { name: /Add comment/i }))[0]);

    const decisionComments = await screen.findAllByLabelText(/decision-comment-/i);
    const decisionCommentBody = decisionComments.find(
      (element) => element.tagName.toLowerCase() === 'textarea',
    ) as HTMLTextAreaElement;
    fireEvent.change(decisionCommentBody, {
      target: { value: 'Need compare on expression before sign-off.' },
    });

    const resolutionFields = screen.getAllByLabelText(/decision-resolution-/i);
    fireEvent.change(resolutionFields[0], {
      target: { value: 'Resolve after comparing hero alt candidate.' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Apply patch/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/storyboard/scene-patch')),
      ).toBe(true);
    });

    const scenePatchCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/storyboard/scene-patch'),
    );
    const scenePatchBody = JSON.parse(String(scenePatchCall?.[1]?.body || '{}'));
    const decisionItems = scenePatchBody.storyboard_scene_patch.decision_items;
    const reviewCandidates = scenePatchBody.storyboard_scene_patch.review_candidates;

    expect(decisionItems[0].resolution_note).toBe('Resolve after comparing hero alt candidate.');
    expect(decisionItems[0].comments[0].body).toBe('Need compare on expression before sign-off.');
    expect(reviewCandidates[0].label).toBe('Hero alt candidate');
  });
});
