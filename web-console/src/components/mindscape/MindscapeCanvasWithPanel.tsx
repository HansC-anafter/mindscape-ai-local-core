'use client';

import React, { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { GraphSidePanel } from './GraphSidePanel';
import { useMindscapeGraph } from '@/lib/mindscape-graph-api';
import { usePendingChanges } from '@/lib/graph-changelog-api';

const MindscapeCanvas = dynamic(
    () => import('./MindscapeCanvas'),
    { ssr: false }
);

export interface MindscapeCanvasWithPanelProps {
    workspaceId?: string;
    workspaceGroupId?: string;
    className?: string;
    showSidePanel?: boolean;
    defaultSidePanelCollapsed?: boolean;
}

export function MindscapeCanvasWithPanel({
    workspaceId,
    workspaceGroupId,
    className = '',
    showSidePanel = true,
    defaultSidePanelCollapsed = false,
}: MindscapeCanvasWithPanelProps) {
    const [isSidePanelCollapsed, setIsSidePanelCollapsed] = useState(defaultSidePanelCollapsed);

    const { refresh: refreshGraph } = useMindscapeGraph({
        workspaceId,
        workspaceGroupId,
        enabled: !!(workspaceId || workspaceGroupId),
    });

    const handleGraphUpdated = useCallback(() => {
        refreshGraph();
    }, [refreshGraph]);

    const toggleSidePanel = useCallback(() => {
        setIsSidePanelCollapsed(prev => !prev);
    }, []);

    const effectiveWorkspaceId = workspaceId || workspaceGroupId || '';

    return (
        <div className={`flex h-full ${className}`}>
            <div className="flex-1 relative">
                <MindscapeCanvas
                    workspaceId={workspaceId || ''}
                    workspaceGroupId={workspaceGroupId}
                    className="w-full h-full"
                />

                {showSidePanel && isSidePanelCollapsed && (
                    <PendingBadge
                        workspaceId={effectiveWorkspaceId}
                        onClick={toggleSidePanel}
                    />
                )}
            </div>

            {showSidePanel && (
                <GraphSidePanel
                    workspaceId={effectiveWorkspaceId}
                    onGraphUpdated={handleGraphUpdated}
                    isCollapsed={isSidePanelCollapsed}
                    onToggleCollapse={toggleSidePanel}
                    className={isSidePanelCollapsed ? 'w-12' : 'w-80'}
                />
            )}
        </div>
    );
}

interface PendingBadgeProps {
    workspaceId: string;
    onClick: () => void;
}

function PendingBadge({ workspaceId, onClick }: PendingBadgeProps) {
    const { totalPending } = usePendingChanges({
        workspaceId,
        enabled: !!workspaceId,
    });

    if (totalPending === 0) return null;

    return (
        <button
            onClick={onClick}
            className="
                absolute top-4 right-4 z-10
                flex items-center gap-2 px-3 py-2
                bg-yellow-100 text-yellow-800
                border border-yellow-200 rounded-lg shadow-md
                hover:bg-yellow-200 transition-colors
            "
        >
            <span className="text-sm font-medium">
                {totalPending} pending changes
            </span>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
        </button>
    );
}

export default MindscapeCanvasWithPanel;
