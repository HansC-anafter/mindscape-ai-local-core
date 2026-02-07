'use client';

/**
 * GraphSidePanel - Combined panel for pending changes and history
 *
 * Tabbed interface that shows:
 * - Pending Changes: Changes awaiting user approval
 * - History: Version-controlled changelog with undo support
 */

import React, { useState, useCallback } from 'react';
import { PendingChangesPanel } from './PendingChangesPanel';
import { GraphHistoryPanel } from './GraphHistoryPanel';
import { usePendingChanges } from '@/lib/graph-changelog-api';

// ============================================================================
// Types
// ============================================================================

type TabType = 'pending' | 'history';

// ============================================================================
// Main Component
// ============================================================================

export interface GraphSidePanelProps {
    workspaceId: string;
    className?: string;
    onGraphUpdated?: () => void;
    defaultTab?: TabType;
    isCollapsed?: boolean;
    onToggleCollapse?: () => void;
}

export function GraphSidePanel({
    workspaceId,
    className = '',
    onGraphUpdated,
    defaultTab = 'pending',
    isCollapsed = false,
    onToggleCollapse,
}: GraphSidePanelProps) {
    const [activeTab, setActiveTab] = useState<TabType>(defaultTab);

    // Get pending count for badge
    const { totalPending } = usePendingChanges({
        workspaceId,
        enabled: !!workspaceId,
    });

    const handleGraphChange = useCallback(() => {
        onGraphUpdated?.();
    }, [onGraphUpdated]);

    // Collapsed state - show just a toggle button
    if (isCollapsed) {
        return (
            <div className={`flex flex-col items-center py-4 bg-white border-l ${className}`}>
                <button
                    onClick={onToggleCollapse}
                    className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded"
                    title="展開側邊面板"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                    </svg>
                </button>
                {totalPending > 0 && (
                    <span className="mt-2 px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">
                        {totalPending}
                    </span>
                )}
            </div>
        );
    }

    return (
        <div className={`flex flex-col h-full bg-white border-l ${className}`}>
            {/* Header with collapse button */}
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
                <div className="flex">
                    {/* Tab Buttons */}
                    <button
                        onClick={() => setActiveTab('pending')}
                        className={`
                            relative px-3 py-1.5 text-sm font-medium rounded-t transition-colors
                            ${activeTab === 'pending'
                                ? 'text-blue-600 bg-white border-t border-x border-gray-200'
                                : 'text-gray-500 hover:text-gray-700'
                            }
                        `}
                    >
                        待審核
                        {totalPending > 0 && (
                            <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded-full">
                                {totalPending}
                            </span>
                        )}
                    </button>
                    <button
                        onClick={() => setActiveTab('history')}
                        className={`
                            px-3 py-1.5 text-sm font-medium rounded-t transition-colors
                            ${activeTab === 'history'
                                ? 'text-blue-600 bg-white border-t border-x border-gray-200'
                                : 'text-gray-500 hover:text-gray-700'
                            }
                        `}
                    >
                        歷史
                    </button>
                </div>
                {onToggleCollapse && (
                    <button
                        onClick={onToggleCollapse}
                        className="p-1 text-gray-400 hover:text-gray-600"
                        title="收合"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                        </svg>
                    </button>
                )}
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-hidden">
                {activeTab === 'pending' ? (
                    <PendingChangesPanel
                        workspaceId={workspaceId}
                        onChangesApplied={handleGraphChange}
                        className="h-full"
                    />
                ) : (
                    <GraphHistoryPanel
                        workspaceId={workspaceId}
                        onUndoComplete={handleGraphChange}
                        className="h-full"
                    />
                )}
            </div>
        </div>
    );
}

export default GraphSidePanel;
