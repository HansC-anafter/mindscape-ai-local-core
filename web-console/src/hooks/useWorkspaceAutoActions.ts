'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getApiBaseUrl } from '@/lib/api-url';
import { Workspace } from '@/app/workspaces/[workspaceId]/workspace-page.types';

const API_URL = getApiBaseUrl();

export function useWorkspaceAutoActions(
    workspaceId: string,
    workspace: Workspace | null,
    loading: boolean
): void {
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        if (!workspace || loading || !pathname) return;

        if (pathname !== `/workspaces/${workspaceId}`) {
            return;
        }

        const launchStatus = (workspace as any).launch_status || 'pending';

        if (launchStatus === 'pending') {
            router.replace(`/workspaces/${workspaceId}/home?setup=true`);
        }
    }, [workspace, loading, workspaceId, router, pathname]);

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

                    const newUrl = new URL(window.location.href);
                    newUrl.searchParams.delete('auto_execute_playbook');
                    newUrl.searchParams.delete('variant_id');
                    window.history.replaceState({}, '', newUrl.toString());

                    window.dispatchEvent(new Event('workspace-chat-updated'));
                } catch {
                }
            };

            const timer = setTimeout(executePlaybook, 500);
            return () => clearTimeout(timer);
        }
    }, [workspace, workspaceId, loading]);

    useEffect(() => {
        if (!workspace || loading) return;

        const params = new URLSearchParams(window.location.search);
        const isMeeting = params.get('meeting') === '1';
        const projectId = params.get('project_id');

        if (!isMeeting || !projectId) return;

        const triggerMeeting = async () => {
            try {
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
                    throw new Error('Meeting auto-trigger failed');
                }

                const newUrl = new URL(window.location.href);
                newUrl.searchParams.delete('meeting');
                newUrl.searchParams.delete('meeting_session_id');
                window.history.replaceState({}, '', newUrl.toString());

                window.dispatchEvent(new Event('workspace-chat-updated'));
            } catch {
            }
        };

        const timer = setTimeout(triggerMeeting, 800);
        return () => clearTimeout(timer);
    }, [workspace, workspaceId, loading]);
}
