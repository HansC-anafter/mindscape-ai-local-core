'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import type { Artifact } from './OutcomesPanel';

const OutcomeDetailModal = dynamic(() => import('../../components/OutcomeDetailModal'), { ssr: false });

interface WorkspaceModalsProps {
    workspaceId: string;
    apiUrl: string;
    selectedArtifact: Artifact | null;
    setSelectedArtifact: (artifact: Artifact | null) => void;
}

export default function WorkspaceModals({
    workspaceId,
    apiUrl,
    selectedArtifact,
    setSelectedArtifact,
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

        </>
    );
}
