'use client';

/**
 * PendingChangesPanel - Display and manage pending graph changes
 *
 * Shows changes suggested by LLM or other sources that require user approval.
 * Supports individual or batch approve/reject operations.
 */

import React, { useState, useCallback } from 'react';
import {
    usePendingChanges,
    approveChanges,
    PendingChange,
} from '@/lib/graph-changelog-api';
import { t } from '@/lib/i18n';

// ============================================================================
// Icons (inline SVGs for simplicity)
// ============================================================================

const CheckIcon = () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
);

const XIcon = () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
);

const NodeIcon = () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="8" strokeWidth={2} />
    </svg>
);

const EdgeIcon = () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
    </svg>
);

const RobotIcon = () => (
    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 2a1 1 0 011 1v1.1A5.002 5.002 0 0115 9v4a1 1 0 01-1 1H6a1 1 0 01-1-1V9a5.002 5.002 0 014-4.9V3a1 1 0 011-1zM5 16a1 1 0 100 2h10a1 1 0 100-2H5z" />
    </svg>
);

// ============================================================================
// Sub-components
// ============================================================================

interface ChangeCardProps {
    change: PendingChange;
    isSelected: boolean;
    onToggleSelect: () => void;
    onApprove: () => void;
    onReject: () => void;
    isProcessing: boolean;
}

function ChangeCard({
    change,
    isSelected,
    onToggleSelect,
    onApprove,
    onReject,
    isProcessing,
}: ChangeCardProps) {
    const operationLabels: Record<string, string> = {
        create_node: '建立節點',
        update_node: '更新節點',
        delete_node: '刪除節點',
        create_edge: '建立連接',
        delete_edge: '刪除連接',
        update_overlay: '更新覆蓋層',
    };

    const actorLabels: Record<string, { label: string; color: string }> = {
        llm: { label: 'AI 建議', color: 'bg-blue-100 text-blue-700' },
        user: { label: '使用者', color: 'bg-green-100 text-green-700' },
        system: { label: '系統', color: 'bg-gray-100 text-gray-700' },
        playbook: { label: 'Playbook', color: 'bg-purple-100 text-purple-700' },
    };

    const actorInfo = actorLabels[change.actor] || actorLabels.system;
    const label = change.after_state?.label || change.target_id;

    return (
        <div
            className={`
                border rounded-lg p-3 mb-2 transition-all duration-200
                ${isSelected ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}
                ${isProcessing ? 'opacity-50 pointer-events-none' : ''}
            `}
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={onToggleSelect}
                        className="rounded border-gray-300"
                        disabled={isProcessing}
                    />
                    <span className="text-gray-500">
                        {change.target_type === 'node' ? <NodeIcon /> : <EdgeIcon />}
                    </span>
                    <span className="text-sm font-medium text-gray-700">
                        {operationLabels[change.operation] || change.operation}
                    </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full flex items-center gap-1 ${actorInfo.color}`}>
                    {change.actor === 'llm' && <RobotIcon />}
                    {actorInfo.label}
                </span>
            </div>

            {/* Content */}
            <div className="ml-6 mb-2">
                <p className="text-sm text-gray-900 font-medium truncate" title={label}>
                    {label}
                </p>
                {change.after_state?.type && (
                    <p className="text-xs text-gray-500">
                        類型: {change.after_state.type}
                    </p>
                )}
                {change.after_state?.reason && (
                    <p className="text-xs text-gray-500 mt-1 italic">
                        "{change.after_state.reason}"
                    </p>
                )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 ml-6">
                <button
                    onClick={onApprove}
                    disabled={isProcessing}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded hover:bg-green-200 transition-colors disabled:opacity-50"
                >
                    <CheckIcon />
                    批准
                </button>
                <button
                    onClick={onReject}
                    disabled={isProcessing}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-red-700 bg-red-100 rounded hover:bg-red-200 transition-colors disabled:opacity-50"
                >
                    <XIcon />
                    拒絕
                </button>
            </div>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export interface PendingChangesPanelProps {
    workspaceId: string;
    className?: string;
    onChangesApplied?: () => void;
}

export function PendingChangesPanel({
    workspaceId,
    className = '',
    onChangesApplied,
}: PendingChangesPanelProps) {
    const { pendingChanges, totalPending, isLoading, isError, refresh } = usePendingChanges({
        workspaceId,
        enabled: !!workspaceId,
    });

    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
    const [isBatchProcessing, setIsBatchProcessing] = useState(false);

    // Toggle selection
    const toggleSelect = useCallback((id: string) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    }, []);

    // Select all
    const selectAll = useCallback(() => {
        setSelectedIds(new Set(pendingChanges.map(c => c.id)));
    }, [pendingChanges]);

    // Deselect all
    const deselectAll = useCallback(() => {
        setSelectedIds(new Set());
    }, []);

    // Handle single approve/reject
    const handleSingleAction = useCallback(async (changeId: string, action: 'approve' | 'reject') => {
        setProcessingIds(prev => new Set(prev).add(changeId));
        try {
            await approveChanges(workspaceId, [changeId], action);
            await refresh();
            onChangesApplied?.();
        } catch (error) {
            console.error(`Failed to ${action} change:`, error);
        } finally {
            setProcessingIds(prev => {
                const next = new Set(prev);
                next.delete(changeId);
                return next;
            });
        }
    }, [workspaceId, refresh, onChangesApplied]);

    // Handle batch approve/reject
    const handleBatchAction = useCallback(async (action: 'approve' | 'reject') => {
        if (selectedIds.size === 0) return;

        setIsBatchProcessing(true);
        setProcessingIds(selectedIds);
        try {
            await approveChanges(workspaceId, Array.from(selectedIds), action);
            setSelectedIds(new Set());
            await refresh();
            onChangesApplied?.();
        } catch (error) {
            console.error(`Failed to ${action} changes:`, error);
        } finally {
            setIsBatchProcessing(false);
            setProcessingIds(new Set());
        }
    }, [workspaceId, selectedIds, refresh, onChangesApplied]);

    // Empty state
    if (!isLoading && pendingChanges.length === 0) {
        return (
            <div className={`p-4 text-center text-gray-500 ${className}`}>
                <p className="text-sm">沒有待審核的變更</p>
            </div>
        );
    }

    return (
        <div className={`flex flex-col h-full ${className}`}>
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b bg-white sticky top-0 z-10">
                <div className="flex items-center gap-2">
                    <h3 className="font-medium text-gray-900">待審核變更</h3>
                    <span className="px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">
                        {totalPending}
                    </span>
                </div>
                <button
                    onClick={() => refresh()}
                    className="text-xs text-gray-500 hover:text-gray-700"
                >
                    重新整理
                </button>
            </div>

            {/* Batch Actions */}
            {pendingChanges.length > 0 && (
                <div className="flex items-center gap-2 p-3 border-b bg-gray-50">
                    <button
                        onClick={selectedIds.size === pendingChanges.length ? deselectAll : selectAll}
                        className="text-xs text-blue-600 hover:text-blue-800"
                    >
                        {selectedIds.size === pendingChanges.length ? '取消全選' : '全選'}
                    </button>
                    {selectedIds.size > 0 && (
                        <>
                            <span className="text-xs text-gray-400">|</span>
                            <button
                                onClick={() => handleBatchAction('approve')}
                                disabled={isBatchProcessing}
                                className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded hover:bg-green-200 disabled:opacity-50"
                            >
                                <CheckIcon />
                                批准選中 ({selectedIds.size})
                            </button>
                            <button
                                onClick={() => handleBatchAction('reject')}
                                disabled={isBatchProcessing}
                                className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-red-700 bg-red-100 rounded hover:bg-red-200 disabled:opacity-50"
                            >
                                <XIcon />
                                拒絕選中
                            </button>
                        </>
                    )}
                </div>
            )}

            {/* Change List */}
            <div className="flex-1 overflow-y-auto p-3">
                {isLoading ? (
                    <div className="flex items-center justify-center h-20">
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500" />
                    </div>
                ) : isError ? (
                    <div className="text-center text-red-500 text-sm p-4">
                        載入失敗，請重試
                    </div>
                ) : (
                    pendingChanges.map(change => (
                        <ChangeCard
                            key={change.id}
                            change={change}
                            isSelected={selectedIds.has(change.id)}
                            onToggleSelect={() => toggleSelect(change.id)}
                            onApprove={() => handleSingleAction(change.id, 'approve')}
                            onReject={() => handleSingleAction(change.id, 'reject')}
                            isProcessing={processingIds.has(change.id)}
                        />
                    ))
                )}
            </div>
        </div>
    );
}

export default PendingChangesPanel;
