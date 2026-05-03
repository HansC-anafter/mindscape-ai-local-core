'use client';

import React, { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useMindscapeGraph, MindscapeNode, MindscapeEdge } from '@/lib/mindscape-graph-api';
import { usePendingChanges } from '@/lib/graph-changelog-api';
import { t } from '@/lib/i18n';

const ReactFlowCanvas = dynamic(
    () => import('./ReactFlowCanvas'),
    {
        ssr: false,
        loading: () => <CanvasLoading />,
    }
);

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
                <div className="text-sm font-semibold mb-2">Warning</div>
                <span className="text-red-600">{message}</span>
            </div>
        </div>
    );
}

function CanvasEmpty() {
    return (
        <div className="w-full h-full bg-gray-50 rounded-lg flex flex-col items-center justify-center border-2 border-dashed border-gray-300">
            <div className="text-center max-w-md px-4">
                <div className="text-sm font-semibold text-gray-500 mb-4">Graph</div>
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

interface MindscapeCanvasProps {
    workspaceId: string;
    workspaceGroupId?: string;
    onNodeSelect?: (node: MindscapeNode | null) => void;
    onNodeContextMenu?: (event: React.MouseEvent, node: MindscapeNode) => void;
    className?: string;
}

export default function MindscapeCanvas({
    workspaceId,
    workspaceGroupId,
    onNodeSelect,
    onNodeContextMenu,
    className = '',
}: MindscapeCanvasProps) {
    const { graph, isLoading, error } = useMindscapeGraph({ workspaceId, workspaceGroupId });
    const { pendingChanges } = usePendingChanges({ workspaceId });

    const nodes = graph?.nodes ?? [];
    const edges = graph?.edges ?? [];

    const pendingNodeIds = useMemo(() => {
        const ids = new Set<string>();
        pendingChanges.forEach(change => {
            if (change.target_type === 'node') {
                ids.add(change.target_id);
            }
        });
        return ids;
    }, [pendingChanges]);

    if (isLoading) {
        return <CanvasLoading />;
    }

    if (error) {
        return <CanvasError message={error} />;
    }

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
