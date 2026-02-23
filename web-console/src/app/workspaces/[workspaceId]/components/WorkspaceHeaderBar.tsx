'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { DeviceStatusIndicator } from '../../components/DeviceStatusIndicator';
import { TrainHeader } from '../../../../components/execution';

interface WorkspaceHeaderBarProps {
    workspace: { title: string };
    workspaceId: string;
    apiUrl: string;
    executionState: {
        trainSteps: any[];
        overallProgress: number;
        isExecuting: boolean;
    };
    selectedThreadId: string | null;
    onWorkspaceNameEdit: () => void;
    onBundleOpen: () => void;
}

export default function WorkspaceHeaderBar({
    workspace,
    workspaceId,
    apiUrl,
    executionState,
    selectedThreadId,
    onWorkspaceNameEdit,
    onBundleOpen,
}: WorkspaceHeaderBarProps) {
    const router = useRouter();

    return (
        <div className="relative">
            <TrainHeader
                workspaceName={workspace.title}
                steps={executionState.trainSteps}
                progress={executionState.overallProgress}
                isExecuting={executionState.isExecuting}
                workspaceId={workspaceId}
                onWorkspaceNameEdit={onWorkspaceNameEdit}
            />
            {/* Action Buttons - Right side of header */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2 z-20">
                {/* Device Status Indicator */}
                <DeviceStatusIndicator apiUrl={apiUrl} />
                {/* Mind Graph Button */}
                <button
                    onClick={() => router.push(`/mindscape/canvas?workspaceId=${workspaceId}`)}
                    className="px-3 py-1.5 text-sm bg-purple-100 dark:bg-purple-900/30 rounded-lg
                     hover:bg-purple-200 dark:hover:bg-purple-800/40 transition-colors
                     flex items-center gap-1.5 text-purple-700 dark:text-purple-300"
                    title="心智執行圖"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <span>Graph</span>
                </button>
                {/* Bundle Button */}
                {selectedThreadId && (
                    <button
                        onClick={onBundleOpen}
                        className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg
                       hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors
                       flex items-center gap-1.5"
                        title="開啟成果包"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                        </svg>
                        <span>Bundle</span>
                    </button>
                )}
            </div>
        </div>
    );
}
