'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { t } from '@/lib/i18n';
import type { Artifact } from './OutcomesPanel';
import type { Workspace } from '../workspace-page.types';

const OutcomeDetailModal = dynamic(() => import('../../components/OutcomeDetailModal'), { ssr: false });
const ConfirmDialog = dynamic(() => import('../../../../components/ConfirmDialog'), { ssr: false });
const SandboxModal = dynamic(() => import('@/components/sandbox/SandboxModal'), { ssr: false });
const WorkspaceSettingsModal = dynamic(() => import('./WorkspaceSettingsModal'), { ssr: false });
const ThreadBundlePanel = dynamic(() => import('../../../../components/workspace/ThreadBundlePanel').then((module) => module.ThreadBundlePanel), { ssr: false });

interface WorkspaceModalsProps {
    workspace: Workspace | null;
    workspaceId: string;
    apiUrl: string;
    // Outcome detail modal
    selectedArtifact: Artifact | null;
    setSelectedArtifact: (artifact: Artifact | null) => void;
    // Delete dialog
    showDeleteDialog: boolean;
    setShowDeleteDialog: (show: boolean) => void;
    isDeleting: boolean;
    setIsDeleting: (deleting: boolean) => void;
    // Sandbox modal
    showSandboxModal: boolean;
    setShowSandboxModal: (show: boolean) => void;
    sandboxId: string | null;
    sandboxProjectId: string | null;
    focusedExecution: any;
    selectedExecutionId: string | null;
    // Full settings modal
    showFullSettings: boolean;
    setShowFullSettings: (show: boolean) => void;
    onSettingsUpdate: () => void;
    // Thread bundle panel
    selectedThreadId: string | null;
    isBundleOpen: boolean;
    setIsBundleOpen: (open: boolean) => void;
}

export default function WorkspaceModals({
    workspace,
    workspaceId,
    apiUrl,
    selectedArtifact,
    setSelectedArtifact,
    showDeleteDialog,
    setShowDeleteDialog,
    isDeleting,
    setIsDeleting,
    showSandboxModal,
    setShowSandboxModal,
    sandboxId,
    sandboxProjectId,
    focusedExecution,
    selectedExecutionId,
    showFullSettings,
    setShowFullSettings,
    onSettingsUpdate,
    selectedThreadId,
    isBundleOpen,
    setIsBundleOpen,
}: WorkspaceModalsProps) {
    const router = useRouter();

    return (
        <>
            {selectedArtifact !== null && (
                <OutcomeDetailModal
                    artifact={selectedArtifact}
                    isOpen={selectedArtifact !== null}
                    onClose={() => setSelectedArtifact(null)}
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                />
            )}

            {showDeleteDialog && (
                <ConfirmDialog
                    isOpen={showDeleteDialog}
                    onClose={() => setShowDeleteDialog(false)}
                    onConfirm={async () => {
                        if (!workspace) return;
                        setIsDeleting(true);
                        try {
                            const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
                                method: 'DELETE',
                            });

                            if (response.ok || response.status === 204) {
                                router.push('/workspaces');
                            } else {
                                const errorData = await response.json().catch(() => ({}));
                                alert(errorData.detail || t('workspaceDeleteFailed' as any));
                                setIsDeleting(false);
                                setShowDeleteDialog(false);
                            }
                        } catch (err) {
                            console.error('Failed to delete workspace:', err);
                            alert(t('workspaceDeleteFailed' as any));
                            setIsDeleting(false);
                            setShowDeleteDialog(false);
                        }
                    }}
                    title={t('workspaceDelete' as any)}
                    message={workspace ? t('workspaceDeleteConfirm', { workspaceName: workspace.title }) : ''}
                    confirmText={t('delete' as any) || 'Delete'}
                    cancelText={t('cancel' as any) || 'Cancel'}
                    confirmButtonClassName="bg-red-600 hover:bg-red-700"
                />
            )}

            {/* Sandbox Modal */}
            {showSandboxModal && sandboxId && (
                <SandboxModal
                    isOpen={showSandboxModal}
                    onClose={() => setShowSandboxModal(false)}
                    workspaceId={workspaceId}
                    sandboxId={sandboxId}
                    projectId={sandboxProjectId || undefined}
                    executionId={focusedExecution?.execution_id || selectedExecutionId || undefined}
                />
            )}

            {showFullSettings && (
                <WorkspaceSettingsModal
                    isOpen={showFullSettings}
                    onClose={() => setShowFullSettings(false)}
                    workspace={workspace ? {
                        ...workspace,
                        execution_mode: workspace.execution_mode ?? undefined,
                        execution_priority: workspace.execution_priority ?? undefined
                    } : null}
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    onUpdate={onSettingsUpdate}
                />
            )}

            {isBundleOpen && (
                <ThreadBundlePanel
                    threadId={selectedThreadId}
                    workspaceId={workspaceId}
                    isOpen={isBundleOpen}
                    onClose={() => setIsBundleOpen(false)}
                    apiUrl={apiUrl}
                />
            )}
        </>
    );
}
