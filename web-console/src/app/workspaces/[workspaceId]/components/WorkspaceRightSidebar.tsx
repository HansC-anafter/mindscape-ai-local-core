'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import ConversationsList from './ConversationsList';
import { ResizablePanel } from '../../../../components/ui/ResizablePanel';
import type { Artifact } from './OutcomesPanel';
import { useT } from '@/lib/i18n';
import type { Workspace } from '../workspace-page.types';

const MindscapeAIWorkbench = dynamic(() => import('../../../../components/MindscapeAIWorkbench'), { ssr: false });
const ResearchModePanel = dynamic(() => import('../../../../components/ResearchModePanel'), { ssr: false });
const PublishingModePanel = dynamic(() => import('../../../../components/PublishingModePanel'), { ssr: false });
const PlanningModePanel = dynamic(() => import('../../../../components/PlanningModePanel'), { ssr: false });
const ExecutionModeSelector = dynamic(() => import('../../../../components/execution/ExecutionModeSelector'), { ssr: false });
const ThinkingContext = dynamic(() => import('../../../../components/execution/ThinkingContext'), { ssr: false });
const AITeamPanel = dynamic(() => import('../../../../components/execution/AITeamPanel'), { ssr: false });
const ArtifactsSummary = dynamic(
    () => import('../../../../components/workspace/ArtifactsSummary').then((module) => module.ArtifactsSummary),
    { ssr: false }
);
const DecisionPanel = dynamic(
    () => import('../../../../components/workspace/DecisionPanel').then((module) => module.DecisionPanel),
    { ssr: false }
);
const WorkflowEvidenceHealthSummary = dynamic(
    () => import('../../../../components/workspace/meeting/WorkflowEvidenceHealthSummary').then((module) => module.WorkflowEvidenceHealthSummary),
    { ssr: false }
);

interface WorkspaceRightSidebarProps {
    workspace: Workspace | null;
    workspaceId: string;
    apiUrl: string;
    executionState: {
        isExecuting: boolean;
        thinkingSummary?: string;
        pipelineStage?: any;
        aiTeamMembers: any[];
        producedArtifacts: any[];
    };
    selectedThreadId: string | null;
    rightSidebarTab: 'timeline' | 'workbench';
    workbenchRefreshTrigger: number;
    setRightSidebarTab: (tab: 'timeline' | 'workbench') => void;
    setSelectedArtifact: (artifact: Artifact | null) => void;
    setLeftSidebarTab: (tab: 'timeline' | 'outcomes') => void;
    setSelectedThreadId: (id: string | null) => void;
    contextData: {
        updateWorkspace: (data: any) => Promise<any>;
    };
}

export default function WorkspaceRightSidebar({
    workspace,
    workspaceId,
    apiUrl,
    executionState,
    selectedThreadId,
    rightSidebarTab,
    workbenchRefreshTrigger,
    setRightSidebarTab,
    setSelectedArtifact,
    setLeftSidebarTab,
    setSelectedThreadId,
    contextData,
}: WorkspaceRightSidebarProps) {
  const t = useT();
    return (
        <div className="w-80 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            {/* Header - Title with AI Team Mode Selector */}
            <div className="flex items-center justify-between border-b dark:border-gray-700 bg-surface dark:bg-gray-800 px-3 py-1.5">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    <h3 className="text-xs font-bold bg-gradient-to-r from-accent dark:from-blue-600 to-gray-600 text-white px-2 py-0.5 rounded-lg shadow-md border border-accent dark:border-blue-700 flex-shrink-0">
                        {t('mindscapeAIWorkbench' as any)}
                    </h3>
                    <div className="h-3 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>
                    {workspace && (
                        <ExecutionModeSelector
                            key={`exec-mode-${workspace.id}-${workspace.execution_mode || 'hybrid'}-${workspace.execution_priority || 'medium'}`}
                            mode={(workspace.execution_mode as 'qa' | 'execution' | 'hybrid' | 'meeting') || 'hybrid'}
                            priority={(workspace.execution_priority as 'low' | 'medium' | 'high') || 'medium'}
                            meetingEnabled={(workspace as any).meeting_enabled !== false}
                            onChange={async (update) => {
                                try {
                                    await contextData.updateWorkspace({
                                        execution_mode: update.mode,
                                        execution_priority: update.priority,
                                    });
                                } catch (err) {
                                    console.error('Failed to update execution mode:', err);
                                }
                            }}
                            onMeetingToggle={async (enabled) => {
                                try {
                                    await contextData.updateWorkspace({
                                        meeting_enabled: enabled,
                                    });
                                } catch (err) {
                                    console.error('Failed to toggle meeting:', err);
                                }
                            }}
                        />
                    )}
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex flex-col">
                <ResizablePanel
                    defaultTopHeight={40}
                    minTopHeight={20}
                    minBottomHeight={20}
                    top={
                        <div className="h-full overflow-hidden border-b dark:border-gray-700">
                            <ConversationsList
                                workspaceId={workspaceId}
                                apiUrl={apiUrl}
                                selectedThreadId={selectedThreadId}
                                onThreadSelect={setSelectedThreadId}
                            />
                        </div>
                    }
                    bottom={
                        <div className="flex-1 flex flex-col overflow-hidden">
                            <ResizablePanel
                                defaultTopHeight={50}
                                minTopHeight={20}
                                minBottomHeight={20}
                                top={
                                    <section className="sidebar-section ai-team-section h-full overflow-hidden flex flex-col">
                                        <div className="flex-1 overflow-y-auto min-h-0 bg-accent-10 dark:bg-blue-900/10">
                                            <div className="p-3">
                                                {(workspace?.execution_mode === 'hybrid' || workspace?.execution_mode === 'execution' || workspace?.execution_mode === 'meeting') && (
                                                    <>
                                                        {executionState.isExecuting && (
                                                            <ThinkingContext
                                                                summary={executionState.thinkingSummary}
                                                                pipelineStage={executionState.pipelineStage}
                                                                isLoading={executionState.isExecuting && !executionState.pipelineStage && !executionState.thinkingSummary}
                                                            />
                                                        )}

                                                        {(() => {
                                                            const shouldShow = executionState.aiTeamMembers.length > 0;
                                                            return shouldShow ? (
                                                                <div className="mt-3">
                                                                    <AITeamPanel
                                                                        members={executionState.aiTeamMembers}
                                                                        isLoading={executionState.isExecuting}
                                                                    />
                                                                </div>
                                                            ) : null;
                                                        })()}
                                                    </>
                                                )}

                                                <ArtifactsSummary
                                                    count={executionState.producedArtifacts.length}
                                                    onViewAll={() => {
                                                        setLeftSidebarTab('outcomes');
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </section>
                                }
                                bottom={
                                    <ResizablePanel
                                        defaultTopHeight={50}
                                        minTopHeight={20}
                                        minBottomHeight={20}
                                        top={
                                            <section className="sidebar-section decision-section h-full overflow-hidden flex flex-col">
                                                <div className="px-3 pt-3">
                                                    <WorkflowEvidenceHealthSummary
                                                        workspaceId={workspaceId}
                                                        apiUrl={apiUrl}
                                                        selectedThreadId={selectedThreadId}
                                                    />
                                                </div>
                                                <DecisionPanel
                                                    workspaceId={workspaceId}
                                                    apiUrl={apiUrl}
                                                    selectedThreadId={selectedThreadId}
                                                    onViewArtifact={setSelectedArtifact}
                                                    onSwitchToOutcomes={() => setLeftSidebarTab('outcomes')}
                                                    workspace={workspace ? {
                                                        playbook_auto_execution_config: (workspace as any)?.playbook_auto_execution_config,
                                                        owner_user_id: (workspace as any)?.owner_user_id
                                                    } : undefined}
                                                />
                                            </section>
                                        }
                                        bottom={
                                            <div className="flex-1 overflow-y-auto min-h-0">
                                                <div className="p-4">
                                                    {workspace && workspace.mode === 'research' && (
                                                        <ResearchModePanel workspaceId={workspaceId} apiUrl={apiUrl} />
                                                    )}
                                                    {workspace && workspace.mode === 'publishing' && (
                                                        <PublishingModePanel workspaceId={workspaceId} apiUrl={apiUrl} />
                                                    )}
                                                    {workspace && workspace.mode === 'planning' && (
                                                        <PlanningModePanel workspaceId={workspaceId} apiUrl={apiUrl} />
                                                    )}
                                                    {workspace && (!workspace.mode || (workspace.mode !== 'research' && workspace.mode !== 'publishing' && workspace.mode !== 'planning')) && (
                                                        <MindscapeAIWorkbench
                                                            workspaceId={workspaceId}
                                                            apiUrl={apiUrl}
                                                            activeTab={rightSidebarTab}
                                                            onTabChange={(tab) => setRightSidebarTab(tab as any)}
                                                            refreshTrigger={workbenchRefreshTrigger}
                                                        />
                                                    )}
                                                </div>
                                            </div>
                                        }
                                    />
                                }
                            />
                        </div>
                    }
                />
            </div>
        </div>
    );
}
