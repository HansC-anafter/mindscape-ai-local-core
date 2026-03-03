import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import WorkspaceInstructionPage from './page';

const mockPush = vi.fn();
const mockRefreshWorkspace = vi.fn();

const baseWorkspace = {
  id: 'ws-test-1',
  title: 'Test Workspace',
  workspace_blueprint: {
    instruction: {
      persona: 'Old persona',
      goals: ['Old goal'],
      anti_goals: [],
      style_rules: [],
      domain_context: 'Old context',
      version: 2,
    },
  },
};

let mockWorkspaceData: any = {
  workspace: baseWorkspace,
  refreshWorkspace: mockRefreshWorkspace,
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ workspaceId: 'ws-test-1' }),
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceData: () => mockWorkspaceData,
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('../components/InstructionChat', () => ({
  default: ({ onApplyPatch }: { onApplyPatch: (patch: any) => void }) => (
    <button type="button" onClick={() => onApplyPatch({ persona: 'Patched persona' })}>
      apply-patch
    </button>
  ),
}));

describe('WorkspaceInstructionPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockRefreshWorkspace.mockReset().mockResolvedValue(undefined);
    mockWorkspaceData = {
      workspace: JSON.parse(JSON.stringify(baseWorkspace)),
      refreshWorkspace: mockRefreshWorkspace,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('loads existing instruction and applies chat patch', async () => {
    render(<WorkspaceInstructionPage />);

    expect(await screen.findByDisplayValue('Old persona')).not.toBeNull();

    fireEvent.click(screen.getByText('apply-patch'));

    expect(await screen.findByDisplayValue('Patched persona')).not.toBeNull();
  });

  it('saves edited instruction to workspace endpoint', async () => {
    render(<WorkspaceInstructionPage />);

    const personaInput = await screen.findByDisplayValue('Old persona');
    fireEvent.change(personaInput, { target: { value: 'New persona' } });

    const saveButton = screen.getByTestId('instruction-save-button');
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    const [url, options] = (global.fetch as any).mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/workspaces/ws-test-1');
    expect(options.method).toBe('PUT');

    const body = JSON.parse(options.body);
    expect(body.workspace_blueprint.instruction.persona).toBe('New persona');
    expect(body.workspace_blueprint.instruction.version).toBe(3);
    expect(mockRefreshWorkspace).toHaveBeenCalledTimes(1);
  });
});
