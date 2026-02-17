'use client';

/**
 * MindscapeCanvasWithPanel - Canvas with integrated side panel
 *
 * Combines the TLDraw canvas with the GraphSidePanel for
 * managing pending changes and viewing history.
 */

import React, { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { GraphSidePanel } from './GraphSidePanel';
import { useMindscapeGraph, MindscapeNode, MindscapeEdge } from '@/lib/mindscape-graph-api';
import { usePendingChanges, PendingChange } from '@/lib/graph-changelog-api';

// Dynamic import of MindscapeCanvas to avoid SSR issues
const MindscapeCanvas = dynamic(
    () => import('./MindscapeCanvas'),
    { ssr: false }
);

// ============================================================================
// Types
// ============================================================================

export interface MindscapeCanvasWithPanelProps {
    workspaceId?: string;
    workspaceGroupId?: string;
    className?: string;
    showSidePanel?: boolean;
    defaultSidePanelCollapsed?: boolean;
}

// ============================================================================
// Main Component
// ============================================================================

export function MindscapeCanvasWithPanel({
    workspaceId,
    workspaceGroupId,
    className = '',
    showSidePanel = true,
    defaultSidePanelCollapsed = false,
}: MindscapeCanvasWithPanelProps) {
    const [isSidePanelCollapsed, setIsSidePanelCollapsed] = useState(defaultSidePanelCollapsed);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

    // Fetch graph data
    const { refresh: refreshGraph } = useMindscapeGraph({
        workspaceId,
        workspaceGroupId,
        enabled: !!(workspaceId || workspaceGroupId),
    });

    // Handle node selection
    const handleNodeSelect = useCallback((node: MindscapeNode | null) => {
        setSelectedNodeId(node?.id ?? null);
    }, []);

    // Handle graph updates from side panel
    const handleGraphUpdated = useCallback(() => {
        refreshGraph();
    }, [refreshGraph]);

    // Toggle side panel
    const toggleSidePanel = useCallback(() => {
        setIsSidePanelCollapsed(prev => !prev);
    }, []);

    const effectiveWorkspaceId = workspaceId || workspaceGroupId || '';

    return (
        <div className={`flex h-full ${className}`}>
            {/* Main Canvas Area */}
            <div className="flex-1 relative">
                <MindscapeCanvas
                    workspaceId={workspaceId || ''}
                    workspaceGroupId={workspaceGroupId}
                    onNodeSelect={handleNodeSelect}
                    className="w-full h-full"
                />

                {/* Floating badge for pending changes (when panel is collapsed) */}
                {showSidePanel && isSidePanelCollapsed && (
                    <PendingBadge
                        workspaceId={effectiveWorkspaceId}
                        onClick={toggleSidePanel}
                    />
                )}
            </div>

            {/* Side Panel */}
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

// ============================================================================
// Helper Components
// ============================================================================

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
                {totalPending} 個待審核變更
            </span>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
        </button>
    );
}

export default MindscapeCanvasWithPanel;
