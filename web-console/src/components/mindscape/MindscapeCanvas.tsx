'use client';

/**
 * MindscapeCanvas - React Flow-based canvas for visualizing mindscape graph
 *
 * This component renders the derived graph + overlay using React Flow's
 * node-based graph capabilities.
 *
 * React Flow is MIT licensed.
 */

import React, { useEffect, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useMindscapeGraph, MindscapeNode, MindscapeEdge } from '@/lib/mindscape-graph-api';
import { usePendingChanges } from '@/lib/graph-changelog-api';
import { t } from '@/lib/i18n';

// ============================================================================
// Dynamic Import for React Flow (SSR-safe)
// ============================================================================

const ReactFlowCanvas = dynamic(
    () => import('./ReactFlowCanvas'),
    {
        ssr: false,
        loading: () => <CanvasLoading />,
    }
);

// ============================================================================
// Helper Components
// ============================================================================

function CanvasLoading() {
    return (
        <div className="w-full h-full bg-gray-50 rounded-lg flex items-center justify-center">
            <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-2" />
                <span className="text-gray-500 text-sm">{t('loading' as any)}</span>
            </div>
        </div>
    );
}

function CanvasError({ message }: { message: string }) {
    return (
        <div className="w-full h-full bg-red-50 rounded-lg flex items-center justify-center">
            <div className="text-center">
                <div className="text-4xl mb-2">⚠️</div>
                <span className="text-red-600">{message}</span>
            </div>
        </div>
    );
}

function CanvasEmpty() {
    return (
        <div className="w-full h-full bg-gray-50 rounded-lg flex flex-col items-center justify-center border-2 border-dashed border-gray-300">
            <div className="text-center max-w-md px-4">
                <div className="text-6xl mb-4">🧠</div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                    {t('mindscapeEmptyTitle' as any) || 'No Mindscape Graph'}
                </h3>
                <p className="text-sm text-gray-600">
                    {t('mindscapeEmptyDescription' as any) || 'Start a conversation to build your mindscape graph.'}
                </p>
            </div>
        </div>
    );
}

// ============================================================================
// Main Canvas Component
// ============================================================================

interface MindscapeCanvasProps {
    workspaceId: string;
    onNodeSelect?: (node: MindscapeNode | null) => void;
    onNodeContextMenu?: (event: React.MouseEvent, node: MindscapeNode) => void;
    className?: string;
}

export default function MindscapeCanvas({
    workspaceId,
    onNodeSelect,
    onNodeContextMenu,
    className = '',
}: MindscapeCanvasProps) {
    const { graph, overlay, isLoading, error } = useMindscapeGraph({ workspaceId });
    const { pendingChanges } = usePendingChanges({ workspaceId });

    const nodes = graph?.nodes ?? [];
    const edges = graph?.edges ?? [];

    // Calculate pending node IDs
    const pendingNodeIds = useMemo(() => {
        const ids = new Set<string>();
        pendingChanges.forEach(change => {
            if (change.target_type === 'node') {
                ids.add(change.target_id);
            }
        });
        return ids;
    }, [pendingChanges]);

    // Loading state
    if (isLoading) {
        return <CanvasLoading />;
    }

    // Error state
    if (error) {
        return <CanvasError message={error} />;
    }

    // Empty state
    if (nodes.length === 0) {
        return <CanvasEmpty />;
    }

    return (
        <div className={`w-full h-full ${className}`}>
            <ReactFlowCanvas
                nodes={nodes}
                edges={edges}
                pendingNodeIds={pendingNodeIds}
                onNodeSelect={onNodeSelect}
                onNodeContextMenu={onNodeContextMenu}
            />
        </div>
    );
}

