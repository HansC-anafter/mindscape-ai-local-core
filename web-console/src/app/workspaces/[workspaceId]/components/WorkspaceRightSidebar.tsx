'use client';

import React from 'react';
import MindscapeAIWorkbench from '../../../../components/MindscapeAIWorkbench';
import ResearchModePanel from '../../../../components/ResearchModePanel';
import PublishingModePanel from '../../../../components/PublishingModePanel';
import PlanningModePanel from '../../../../components/PlanningModePanel';
import ConversationsList from './ConversationsList';
import ExecutionChatPanel from '../../components/ExecutionChatPanel';
import {
    ExecutionModeSelector,
    ThinkingContext,
} from '../../../../components/execution';
import AITeamPanel from '../../../../components/execution/AITeamPanel';
import { ArtifactsSummary } from '../../../../components/workspace/ArtifactsSummary';
import { DecisionPanel } from '../../../../components/workspace/DecisionPanel';
import { ResizablePanel } from '../../../../components/ui/ResizablePanel';
import { Artifact } from './OutcomesPanel';
import { t } from '@/lib/i18n';
import { Workspace } from '../workspace-page.types';

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
    focusExecutionId: string | null;
    focusedExecution: any;
    focusedPlaybookMetadata: any;
    selectedThreadId: string | null;
    rightSidebarTab: 'timeline' | 'workbench';
    workbenchRefreshTrigger: number;
    setRightSidebarTab: (tab: 'timeline' | 'workbench') => void;
    setSelectedArtifact: (artifact: Artifact | null) => void;
    setLeftSidebarTab: (tab: 'timeline' | 'outcomes' | 'pack') => void;
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
    focusExecutionId,
    focusedExecution,
    focusedPlaybookMetadata,
    selectedThreadId,
    rightSidebarTab,
    workbenchRefreshTrigger,
    setRightSidebarTab,
    setSelectedArtifact,
    setLeftSidebarTab,
    setSelectedThreadId,
    contextData,
}: WorkspaceRightSidebarProps) {
    return (
        <div className="w-80 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            {/* Header - Title with AI Team Mode Selector */}
            <div className="flex items-center justify-between border-b dark:border-gray-700 bg-surface dark:bg-gray-800 px-3 py-1.5">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    <h3 className="text-xs font-bold bg-gradient-to-r from-accent dark:from-blue-600 to-gray-600 text-white px-2 py-0.5 rounded-lg shadow-md border border-accent dark:border-blue-700 flex-shrink-0">
                        {t('mindscapeAIWorkbench' as any)}
                    </h3>
                    <div className="h-3 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>
                    {focusExecutionId ? (
                        <div className="flex items-center gap-1 flex-shrink-0">
                            <h3 className="text-xs font-semibold text-primary dark:text-gray-100">
                                {focusedPlaybookMetadata?.title || focusedExecution?.playbook_code || t('playbookConversation' as any)}
                            </h3>
                        </div>
                    ) : (
                        /* AI Team + Execution Mode integrated */
                        workspace && (
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
                        )
                    )}
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex flex-col">
                <ResizablePanel
                    defaultTopHeight={focusExecutionId ? 30 : 40}
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
                        focusExecutionId ? (
                            // Mode B (Playbook Perspective): Show Execution Chat
                            <div className="h-full overflow-hidden">
                                <ExecutionChatPanel
                                    key={focusExecutionId}
                                    executionId={focusExecutionId}
                                    workspaceId={workspaceId}
                                    apiUrl={apiUrl}
                                    playbookMetadata={focusedPlaybookMetadata}
                                />
                            </div>
                        ) : (
                            // Mode A (Workspace Perspective): Show Workspace Tools
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
                                                                // Show AI Team if there are members, regardless of execution state
                                                                // AI Team should be visible even when not actively executing (shows recent/relevant team members)
                                                                const shouldShow = executionState.aiTeamMembers.length > 0;
                                                                console.log('[WorkspacePage] AITeamPanel render check:', {
                                                                    aiTeamMembersCount: executionState.aiTeamMembers.length,
                                                                    pipelineStage: executionState.pipelineStage?.stage,
                                                                    isExecuting: executionState.isExecuting,
                                                                    shouldShow,
                                                                    members: executionState.aiTeamMembers,
                                                                    executionMode: workspace?.execution_mode
                                                                });
                                                                if (shouldShow) {
                                                                    console.log('[WorkspacePage] Rendering AITeamPanel with members:', executionState.aiTeamMembers);
                                                                } else {
                                                                    console.log('[WorkspacePage] Not rendering AITeamPanel - no members');
                                                                }
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
                                                            // Switch to left sidebar outcomes tab
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
                                                    <DecisionPanel
                                                        workspaceId={workspaceId}
                                                        apiUrl={apiUrl}
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
                        )
                    }
                />
            </div>
        </div>
    );
}
