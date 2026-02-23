'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getApiBaseUrl } from '@/lib/api-url';
import { Workspace } from '@/app/workspaces/[workspaceId]/workspace-page.types';

const API_URL = getApiBaseUrl();

/**
 * Handles URL-parameter-driven auto-actions for a workspace page:
 * 1. Route by launch_status (pending → /home?setup=true)
 * 2. Auto-execute playbook when ?auto_execute_playbook=true
 * 3. Auto-trigger meeting when ?meeting=1
 *
 * Pure side-effect hook — no return value.
 * Extracted from WorkspacePageContent to reduce page.tsx complexity.
 */
export function useWorkspaceAutoActions(
    workspaceId: string,
    workspace: Workspace | null,
    loading: boolean
): void {
    const router = useRouter();
    const pathname = usePathname();

    // Route by launch_status (state machine routing)
    // IMPORTANT: Only redirect pending workspaces to setup, don't force ready/active to home
    // This preserves the original "click to work" behavior
    useEffect(() => {
        if (!workspace || loading || !pathname) return;

        // Check if we're already on a specific route (home or work)
        // Only redirect if we're on the base /workspaces/:id route
        if (pathname !== `/workspaces/${workspaceId}`) {
            // Already on a specific route (home/work), don't auto-redirect
            return;
        }

        // Route based on launch_status
        const launchStatus = (workspace as any).launch_status || 'pending';
        console.log(`[WorkspacePage] Routing workspace ${workspaceId} with status: ${launchStatus}`);

        // ONLY redirect pending workspaces to setup
        // ready and active should stay on work page (preserve original behavior)
        if (launchStatus === 'pending') {
            // New workspace needs setup - redirect to home with setup drawer
            console.log(`[WorkspacePage] Redirecting pending workspace to /home?setup=true`);
            router.replace(`/workspaces/${workspaceId}/home?setup=true`);
        }
        // ready and active: stay on work page (no redirect)
        // Users can navigate to /home manually if they want to see Launchpad
    }, [workspace, loading, workspaceId, router, pathname]);

    // Auto-execute playbook when workspace is loaded with auto_execute_playbook parameter
    useEffect(() => {
        if (!workspace || loading) return;

        const searchParams = new URLSearchParams(window.location.search);
        const autoExecute = searchParams?.get('auto_execute_playbook') === 'true';
        const variantId = searchParams?.get('variant_id');

        if (autoExecute && workspace.default_playbook_id) {
            const executePlaybook = async () => {
                try {
                    const actionParams: any = {
                        playbook_code: workspace.default_playbook_id
                    };

                    if (variantId) {
                        actionParams.variant_id = variantId;
                    }

                    const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/chat`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            action: 'execute_playbook',
                            action_params: actionParams
                        })
                    });

                    if (!response.ok) {
                        throw new Error('Failed to execute playbook');
                    }

                    // Clear URL parameters to avoid re-execution on refresh
                    const newUrl = new URL(window.location.href);
                    newUrl.searchParams.delete('auto_execute_playbook');
                    newUrl.searchParams.delete('variant_id');
                    window.history.replaceState({}, '', newUrl.toString());

                    // Trigger workspace chat update event to refresh messages
                    window.dispatchEvent(new Event('workspace-chat-updated'));
                } catch (err: any) {
                    console.error('Failed to auto-execute playbook:', err);
                }
            };

            // Small delay to ensure workspace chat is ready
            const timer = setTimeout(executePlaybook, 500);
            return () => clearTimeout(timer);
        }
    }, [workspace, workspaceId, loading]);

    // Auto-trigger meeting mode when URL contains meeting=1
    useEffect(() => {
        if (!workspace || loading) return;

        const params = new URLSearchParams(window.location.search);
        const isMeeting = params.get('meeting') === '1';
        const projectId = params.get('project_id');

        if (!isMeeting || !projectId) return;

        const triggerMeeting = async () => {
            try {
                console.log('[WorkspacePage] Auto-triggering meeting for project:', projectId);

                const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: '[Meeting Started] Project persistent meeting started',
                        project_id: projectId,
                        thread_id: params.get('meeting_session_id') || undefined,
                    }),
                });

                if (!response.ok) {
                    console.error('[WorkspacePage] Meeting auto-trigger failed:', response.status);
                }

                // Clear meeting param to prevent re-trigger on refresh
                const newUrl = new URL(window.location.href);
                newUrl.searchParams.delete('meeting');
                newUrl.searchParams.delete('meeting_session_id');
                window.history.replaceState({}, '', newUrl.toString());

                // Refresh chat to show meeting events
                window.dispatchEvent(new Event('workspace-chat-updated'));
            } catch (err) {
                console.error('[WorkspacePage] Failed to auto-trigger meeting:', err);
            }
        };

        const timer = setTimeout(triggerMeeting, 800);
        return () => clearTimeout(timer);
    }, [workspace, workspaceId, loading]);
}
