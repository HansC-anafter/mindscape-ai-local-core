import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWorkspaceAutoActions } from '../useWorkspaceAutoActions';

// Mock next/navigation
const mockRouterPush = vi.fn();
const mockRouterReplace = vi.fn();
let mockPathname = '/workspaces/ws-test-123';

vi.mock('next/navigation', () => ({
    useRouter: () => ({
        push: mockRouterPush,
        replace: mockRouterReplace,
    }),
    usePathname: () => mockPathname,
}));

// Mock api-url
vi.mock('@/lib/api-url', () => ({
    getApiBaseUrl: () => 'http://localhost:8000',
}));

// Mock workspace-page.types (just needs to be importable)
vi.mock('@/app/workspaces/[workspaceId]/workspace-page.types', () => ({}));

describe('useWorkspaceAutoActions', () => {
    const workspaceId = 'ws-test-123';

    beforeEach(() => {
        mockRouterPush.mockClear();
        mockRouterReplace.mockClear();
        vi.useFakeTimers();
        mockPathname = `/workspaces/${workspaceId}`;

        // Reset window.location.search
        Object.defineProperty(window, 'location', {
            value: {
                search: '',
                href: `http://localhost:3000/workspaces/${workspaceId}`,
            },
            writable: true,
        });

        // Mock window.history.replaceState
        window.history.replaceState = vi.fn();

        // Mock window.dispatchEvent
        window.dispatchEvent = vi.fn().mockReturnValue(true);

        // Default fetch mock
        global.fetch = vi.fn().mockResolvedValue({ ok: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    describe('launch_status routing', () => {
        it('should redirect pending workspace to /home?setup=true', () => {
            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'pending',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            expect(mockRouterReplace).toHaveBeenCalledWith(
                `/workspaces/${workspaceId}/home?setup=true`
            );
        });

        it('should NOT redirect ready workspace', () => {
            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'ready',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            expect(mockRouterReplace).not.toHaveBeenCalled();
        });

        it('should NOT redirect active workspace', () => {
            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            expect(mockRouterReplace).not.toHaveBeenCalled();
        });

        it('should NOT redirect when already on a sub-route', () => {
            mockPathname = `/workspaces/${workspaceId}/home`;

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'pending',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            expect(mockRouterReplace).not.toHaveBeenCalled();
        });

        it('should do nothing while loading', () => {
            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'pending',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, true)
            );

            expect(mockRouterReplace).not.toHaveBeenCalled();
        });

        it('should do nothing when workspace is null', () => {
            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, null, false)
            );

            expect(mockRouterReplace).not.toHaveBeenCalled();
        });
    });

    describe('auto-execute playbook', () => {
        it('should auto-execute playbook when URL param is set', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?auto_execute_playbook=true',
                    href: `http://localhost:3000/workspaces/${workspaceId}?auto_execute_playbook=true`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
                default_playbook_id: 'pb-001',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            // Advance past the 500ms delay
            await vi.advanceTimersByTimeAsync(600);

            expect(global.fetch).toHaveBeenCalledWith(
                `http://localhost:8000/api/v1/workspaces/${workspaceId}/chat`,
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('execute_playbook'),
                })
            );
        });

        it('should include variant_id when present in URL', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?auto_execute_playbook=true&variant_id=var-99',
                    href: `http://localhost:3000/workspaces/${workspaceId}?auto_execute_playbook=true&variant_id=var-99`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
                default_playbook_id: 'pb-001',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            await vi.advanceTimersByTimeAsync(600);

            const fetchBody = JSON.parse((global.fetch as any).mock.calls.at(-1)[1].body);
            expect(fetchBody.action_params.variant_id).toBe('var-99');
        });

        it('should NOT auto-execute when no default_playbook_id', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?auto_execute_playbook=true',
                    href: `http://localhost:3000/workspaces/${workspaceId}?auto_execute_playbook=true`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
                // no default_playbook_id
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            await vi.advanceTimersByTimeAsync(600);

            // fetch should not have been called for playbook execution
            const playbookCalls = (global.fetch as any).mock.calls.filter(
                (call: any[]) => call[0].includes('/chat')
            );
            expect(playbookCalls).toHaveLength(0);
        });
    });

    describe('auto-trigger meeting', () => {
        it('should trigger meeting when URL params are set', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?meeting=1&project_id=proj-42',
                    href: `http://localhost:3000/workspaces/${workspaceId}?meeting=1&project_id=proj-42`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            // Advance past the 800ms delay
            await vi.advanceTimersByTimeAsync(900);

            expect(global.fetch).toHaveBeenCalledWith(
                `http://localhost:8000/api/v1/workspaces/${workspaceId}/chat`,
                expect.objectContaining({
                    method: 'POST',
                    body: expect.stringContaining('Meeting Started'),
                })
            );
        });

        it('should include meeting_session_id as thread_id', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?meeting=1&project_id=proj-42&meeting_session_id=sess-77',
                    href: `http://localhost:3000/workspaces/${workspaceId}?meeting=1&project_id=proj-42&meeting_session_id=sess-77`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            await vi.advanceTimersByTimeAsync(900);

            const fetchBody = JSON.parse((global.fetch as any).mock.calls.at(-1)[1].body);
            expect(fetchBody.thread_id).toBe('sess-77');
        });

        it('should NOT trigger meeting without project_id', async () => {
            Object.defineProperty(window, 'location', {
                value: {
                    search: '?meeting=1',
                    href: `http://localhost:3000/workspaces/${workspaceId}?meeting=1`,
                },
                writable: true,
            });

            const workspace = {
                id: workspaceId,
                title: 'Test',
                launch_status: 'active',
            };

            renderHook(() =>
                useWorkspaceAutoActions(workspaceId, workspace as any, false)
            );

            await vi.advanceTimersByTimeAsync(900);

            const meetingCalls = (global.fetch as any).mock.calls.filter(
                (call: any[]) => call[0].includes('/chat')
            );
            expect(meetingCalls).toHaveLength(0);
        });
    });
});
