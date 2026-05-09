'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import type { Artifact } from './OutcomesPanel';

const OutcomeDetailModal = dynamic(() => import('../../components/OutcomeDetailModal'), { ssr: false });
const ThreadBundlePanel = dynamic(() => import('../../../../components/workspace/ThreadBundlePanel').then((module) => module.ThreadBundlePanel), { ssr: false });

interface WorkspaceModalsProps {
    workspaceId: string;
    apiUrl: string;
    // Outcome detail modal
    selectedArtifact: Artifact | null;
    setSelectedArtifact: (artifact: Artifact | null) => void;
    // Thread bundle panel
    selectedThreadId: string | null;
    isBundleOpen: boolean;
    setIsBundleOpen: (open: boolean) => void;
}

export default function WorkspaceModals({
    workspaceId,
    apiUrl,
    selectedArtifact,
    setSelectedArtifact,
    selectedThreadId,
    isBundleOpen,
    setIsBundleOpen,
}: WorkspaceModalsProps) {
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
