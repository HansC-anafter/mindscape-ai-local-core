'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import OutcomeDetailModal from '../../components/OutcomeDetailModal';
import ConfirmDialog from '../../../../components/ConfirmDialog';
import SandboxModal from '@/components/sandbox/SandboxModal';
import WorkspaceSettingsModal from './WorkspaceSettingsModal';
import { ThreadBundlePanel } from '../../../../components/workspace/ThreadBundlePanel';
import { t } from '@/lib/i18n';
import { Artifact } from './OutcomesPanel';
import { Workspace } from '../workspace-page.types';

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
            <OutcomeDetailModal
                artifact={selectedArtifact}
                isOpen={selectedArtifact !== null}
                onClose={() => setSelectedArtifact(null)}
                workspaceId={workspaceId}
                apiUrl={apiUrl}
            />

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
                confirmText={t('delete' as any) || '刪除'}
                cancelText={t('cancel' as any) || '取消'}
                confirmButtonClassName="bg-red-600 hover:bg-red-700"
            />

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

            {/* Thread Bundle Panel */}
            <ThreadBundlePanel
                threadId={selectedThreadId}
                workspaceId={workspaceId}
                isOpen={isBundleOpen}
                onClose={() => setIsBundleOpen(false)}
                apiUrl={apiUrl}
            />
        </>
    );
}
