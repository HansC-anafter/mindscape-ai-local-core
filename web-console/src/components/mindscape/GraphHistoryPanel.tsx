'use client';

/**
 * GraphHistoryPanel - Display graph changelog history
 *
 * Shows the version-controlled history of graph changes with undo support.
 */

import React, { useState, useCallback } from 'react';
import { useGraphHistory, undoChange, HistoryEntry } from '@/lib/graph-changelog-api';

// ============================================================================
// Icons
// ============================================================================

const UndoIcon = () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
    </svg>
);

// ============================================================================
// Sub-components
// ============================================================================

interface HistoryItemProps {
    entry: HistoryEntry;
    onUndo?: () => void;
    isUndoing: boolean;
}

function HistoryItem({ entry, onUndo, isUndoing }: HistoryItemProps) {
    const operationLabels: Record<string, string> = {
        create_node: '建立節點',
        update_node: '更新節點',
        delete_node: '刪除節點',
        create_edge: '建立連接',
        delete_edge: '刪除連接',
        update_overlay: '更新覆蓋層',
    };

    const statusColors: Record<string, string> = {
        applied: 'bg-green-100 text-green-700',
        undone: 'bg-gray-100 text-gray-500 line-through',
        pending: 'bg-yellow-100 text-yellow-700',
        rejected: 'bg-red-100 text-red-700',
    };

    const actorIcons: Record<string, string> = {
        llm: '🤖',
        user: '👤',
        system: '⚙️',
        playbook: '📋',
    };

    const canUndo = entry.status === 'applied';
    const formatTime = (dateStr?: string) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className={`
            flex items-center justify-between p-2 border-b border-gray-100
            ${entry.status === 'undone' ? 'opacity-50' : ''}
        `}>
            <div className="flex items-center gap-2 flex-1 min-w-0">
                <span className="text-xs text-gray-400 w-8">v{entry.version}</span>
                <span>{actorIcons[entry.actor] || '❓'}</span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-700 truncate">
                        {operationLabels[entry.operation] || entry.operation}
                    </p>
                    <p className="text-xs text-gray-400 truncate">
                        {entry.target_id.substring(0, 20)}...
                    </p>
                </div>
            </div>
            <div className="flex items-center gap-2">
                <span className={`text-xs px-1.5 py-0.5 rounded ${statusColors[entry.status] || 'bg-gray-100'}`}>
                    {entry.status}
                </span>
                <span className="text-xs text-gray-400">
                    {formatTime(entry.applied_at || entry.created_at)}
                </span>
                {canUndo && onUndo && (
                    <button
                        onClick={onUndo}
                        disabled={isUndoing}
                        className="p-1 text-gray-400 hover:text-blue-600 disabled:opacity-50"
                        title="撤銷"
                    >
                        <UndoIcon />
                    </button>
                )}
            </div>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export interface GraphHistoryPanelProps {
    workspaceId: string;
    className?: string;
    onUndoComplete?: () => void;
}

export function GraphHistoryPanel({
    workspaceId,
    className = '',
    onUndoComplete,
}: GraphHistoryPanelProps) {
    const { history, currentVersion, isLoading, isError, refresh } = useGraphHistory({
        workspaceId,
        limit: 30,
        enabled: !!workspaceId,
    });

    const [undoingId, setUndoingId] = useState<string | null>(null);

    const handleUndo = useCallback(async (changeId: string) => {
        setUndoingId(changeId);
        try {
            await undoChange(changeId);
            await refresh();
            onUndoComplete?.();
        } catch (error) {
            console.error('Failed to undo change:', error);
        } finally {
            setUndoingId(null);
        }
    }, [refresh, onUndoComplete]);

    return (
        <div className={`flex flex-col h-full bg-white ${className}`}>
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b sticky top-0 bg-white z-10">
                <div className="flex items-center gap-2">
                    <h3 className="font-medium text-gray-900">變更歷史</h3>
                    <span className="text-xs text-gray-500">
                        v{currentVersion}
                    </span>
                </div>
                <button
                    onClick={() => refresh()}
                    className="text-xs text-gray-500 hover:text-gray-700"
                >
                    重新整理
                </button>
            </div>

            {/* History List */}
            <div className="flex-1 overflow-y-auto">
                {isLoading ? (
                    <div className="flex items-center justify-center h-20">
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500" />
                    </div>
                ) : isError ? (
                    <div className="text-center text-red-500 text-sm p-4">
                        載入失敗
                    </div>
                ) : history.length === 0 ? (
                    <div className="text-center text-gray-500 text-sm p-4">
                        尚無歷史記錄
                    </div>
                ) : (
                    history.map(entry => (
                        <HistoryItem
                            key={entry.id}
                            entry={entry}
                            onUndo={() => handleUndo(entry.id)}
                            isUndoing={undoingId === entry.id}
                        />
                    ))
                )}
            </div>
        </div>
    );
}

export default GraphHistoryPanel;
