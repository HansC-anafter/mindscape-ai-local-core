import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useWorkspaceProjects } from '../useWorkspaceProjects';

// Mock next/navigation
const mockSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
    useSearchParams: () => mockSearchParams,
}));

// Mock api-url
vi.mock('@/lib/api-url', () => ({
    getApiBaseUrl: () => 'http://localhost:8000',
}));

// Mock workspace-page.types (just needs to be importable)
vi.mock('@/app/workspaces/[workspaceId]/workspace-page.types', () => ({}));

const API_URL = 'http://localhost:8000';

describe('useWorkspaceProjects', () => {
    const workspaceId = 'ws-test-123';

    const mockProjects = [
        { id: 'proj-1', title: 'Project Alpha', type: 'content' },
        { id: 'proj-2', title: 'Project Beta', type: 'research' },
    ];

    const mockWorkspace = {
        id: workspaceId,
        title: 'Test Workspace',
        primary_project_id: 'proj-1',
    };

    beforeEach(() => {
        vi.restoreAllMocks();
        // Reset URL search params
        mockSearchParams.delete('project_id');
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('should initialize with empty state', () => {
        // Prevent fetch from actually running
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: [] }),
        });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, null)
        );

        expect(result.current.projects).toEqual([]);
        expect(result.current.currentProject).toBeNull();
        expect(result.current.selectedProjectId).toBeNull();
        expect(result.current.selectedType).toBeNull();
        expect(result.current.isLoadingProjects).toBe(true); // starts loading immediately
    });

    it('should load projects on mount', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: mockProjects }),
        });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(result.current.isLoadingProjects).toBe(false);
        });

        expect(result.current.projects).toEqual(mockProjects);
        // Should select primary_project_id from workspace
        expect(result.current.selectedProjectId).toBe('proj-1');
    });

    it('should use URL project_id param over workspace primary', async () => {
        mockSearchParams.set('project_id', 'proj-2');

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: mockProjects }),
        });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(result.current.isLoadingProjects).toBe(false);
        });

        expect(result.current.selectedProjectId).toBe('proj-2');
    });

    it('should fall back to first project when no primary set', async () => {
        const workspaceNoPrimary = { id: workspaceId, title: 'Test', primary_project_id: undefined };

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: mockProjects }),
        });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, workspaceNoPrimary as any)
        );

        await waitFor(() => {
            expect(result.current.isLoadingProjects).toBe(false);
        });

        expect(result.current.selectedProjectId).toBe('proj-1');
    });

    it('should handle API failure gracefully', async () => {
        global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(result.current.isLoadingProjects).toBe(false);
        });

        expect(result.current.projects).toEqual([]);
    });

    it('should filter by selectedType', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: mockProjects }),
        });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(result.current.isLoadingProjects).toBe(false);
        });

        // Change type filter
        act(() => {
            result.current.setSelectedType('research');
        });

        // Should trigger a new fetch with project_type param
        await waitFor(() => {
            const lastCall = (global.fetch as any).mock.calls.at(-1);
            const url = lastCall[0].toString();
            expect(url).toContain('project_type=research');
        });
    });

    it('should call correct API endpoint', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ projects: [] }),
        });

        renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });

        const firstCallUrl = (global.fetch as any).mock.calls[0][0].toString();
        expect(firstCallUrl).toContain(`${API_URL}/api/v1/workspaces/${workspaceId}/projects`);
        expect(firstCallUrl).toContain('state=open');
        expect(firstCallUrl).toContain('limit=20');
    });

    it('should load individual project after selection', async () => {
        const mockProjectDetail = { id: 'proj-1', title: 'Project Alpha', type: 'content', description: 'detailed' };

        global.fetch = vi.fn()
            .mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve({ projects: mockProjects }),
            })
            .mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(mockProjectDetail),
            });

        const { result } = renderHook(() =>
            useWorkspaceProjects(workspaceId, mockWorkspace as any)
        );

        await waitFor(() => {
            expect(result.current.currentProject).not.toBeNull();
        });

        // Verify project detail was fetched
        const detailCalls = (global.fetch as any).mock.calls.filter(
            (call: any[]) => call[0].toString().includes(`/projects/proj-1`) && !call[0].toString().includes('?')
        );
        expect(detailCalls.length).toBeGreaterThan(0);
    });
});
