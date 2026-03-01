'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import IntegratedSystemStatusCard from '../../../../components/IntegratedSystemStatusCard';
import StoragePathConfigModal from '@/components/StoragePathConfigModal';
import TimelinePanel from '../../components/TimelinePanel';
import LeftSidebarTabs from './LeftSidebarTabs';
import ProjectCard from './ProjectCard';
import ProjectSubTabs from './ProjectSubTabs';
import { PackPanel } from './PackPanel';
import RuntimeSettingsModal from './RuntimeSettingsModal';
import WorkspaceInstructionModal from './WorkspaceInstructionModal';
import { Project } from '@/types/project';
import { Workspace } from '../workspace-page.types';

interface WorkspaceLeftSidebarProps {
    workspace: Workspace | null;
    workspaceId: string;
    apiUrl: string;
    systemStatus: any;
    projects: Project[];
    currentProject: Project | null;
    selectedProjectId: string | null;
    selectedType: string | null;
    isLoadingProject: boolean;
    leftSidebarTab: 'timeline' | 'outcomes' | 'pack';
    setLeftSidebarTab: (tab: 'timeline' | 'outcomes' | 'pack') => void;
    setSelectedType: (type: string | null) => void;
    onProjectSelect: (project: Project) => void;
    showSystemTools: boolean;
    setShowSystemTools: (show: boolean) => void;
    showDataSourcesModal: boolean;
    setShowDataSourcesModal: (show: boolean) => void;
    showRuntimeModal: boolean;
    setShowRuntimeModal: (show: boolean) => void;
    showInstructionModal: boolean;
    setShowInstructionModal: (show: boolean) => void;
    onRefreshAll: () => void;
}

export default function WorkspaceLeftSidebar({
    workspace,
    workspaceId,
    apiUrl,
    systemStatus,
    projects,
    currentProject,
    selectedProjectId,
    selectedType,
    isLoadingProject,
    leftSidebarTab,
    setLeftSidebarTab,
    setSelectedType,
    onProjectSelect,
    showSystemTools,
    setShowSystemTools,
    showDataSourcesModal,
    setShowDataSourcesModal,
    showRuntimeModal,
    setShowRuntimeModal,
    showInstructionModal,
    setShowInstructionModal,
    onRefreshAll,
}: WorkspaceLeftSidebarProps) {
    const router = useRouter();

    return (
        <div className="w-80 border-r dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            {/* Tab Panel Section - Top */}
            <div className="flex-1 overflow-hidden min-h-0">
                <LeftSidebarTabs
                    activeTab={leftSidebarTab}
                    onTabChange={setLeftSidebarTab}
                    timelineContent={
                        <div className="flex flex-col h-full">
                            {projects.length > 0 && (
                                <ProjectSubTabs
                                    projects={projects}
                                    selectedType={selectedType}
                                    selectedProjectId={selectedProjectId}
                                    onTypeChange={setSelectedType}
                                    onProjectSelect={(project) => {
                                        onProjectSelect(project);
                                    }}
                                />
                            )}

                            {/* Project Card */}
                            <div className="flex-shrink-0 border-b dark:border-gray-700 p-3">
                                {isLoadingProject ? (
                                    <div className="text-xs text-secondary dark:text-gray-400">
                                        載入中...
                                    </div>
                                ) : currentProject ? (
                                    <ProjectCard
                                        project={currentProject}
                                        workspaceId={workspaceId}
                                        apiUrl={apiUrl}
                                        defaultExpanded={true}
                                        onOpenExecution={(executionId) => {
                                            // Navigate to dedicated execution page
                                            const executionUrl = `/workspaces/${workspaceId}/executions/${executionId}`;
                                            console.log('[WorkspacePage] ProjectCard onOpenExecution, navigating to:', executionUrl);
                                            router.push(executionUrl);
                                        }}
                                    />
                                ) : (
                                    <div className="px-3 py-2">
                                        <div className="project-placeholder text-center py-8">
                                            <div className="text-2xl mb-2">📁</div>
                                            <div className="text-sm font-medium text-primary dark:text-gray-300 mb-1">
                                                尚無進行中的專案
                                            </div>
                                            <div className="text-xs text-secondary dark:text-gray-400">
                                                開始對話後，系統會自動建立專案
                                            </div>
                                            {/* Debug info */}
                                            {process.env.NODE_ENV === 'development' && (
                                                <div className="mt-4 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-left">
                                                    <div><strong>🔍 Debug Info:</strong></div>
                                                    <div>workspace.primary_project_id: {workspace?.primary_project_id || '❌ null'}</div>
                                                    <div>currentProject exists: {currentProject ? '✅ YES' : '❌ NO'}</div>
                                                    <div>isLoadingProject: {isLoadingProject ? '⏳ true' : '✅ false'}</div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Left sidebar primarily shows project card */}
                        </div>
                    }
                    outcomesContent={
                        <TimelinePanel
                            workspaceId={workspaceId}
                            apiUrl={apiUrl}
                            isInSettingsPage={false}
                            showArchivedOnly={true}
                        />
                    }
                    packContent={
                        <PackPanel
                            workspaceId={workspaceId}
                            apiUrl={apiUrl}
                            storyThreadId={workspace?.primary_project_id ? undefined : undefined}
                        />
                    }
                />
            </div>

            {/* Workspace Settings - Collapsible at bottom */}
            {workspace && (
                <div className="border-t dark:border-gray-700 bg-surface-secondary dark:bg-orange-900/10 mt-auto">
                    {/* Settings Entry - Collapsible in left sidebar */}
                    <div className="border-t dark:border-gray-700">
                        <div
                            className="px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                            onClick={() => setShowSystemTools(!showSystemTools)}
                        >
                            <div className="flex items-center gap-2">
                                <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                <div>
                                    <div className="text-xs font-medium text-primary dark:text-gray-300">工作區設定</div>
                                    <div className="text-[10px] text-tertiary">模式 · 產物 · 偏好 · 資料來源</div>
                                </div>
                            </div>
                            <span className="text-tertiary text-xs">{showSystemTools ? '▲' : '▼'}</span>
                        </div>

                        {/* Collapsible Settings Panel */}
                        <div
                            className={`border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out ${showSystemTools ? 'max-h-[400px] opacity-100' : 'max-h-0 opacity-0'
                                }`}
                        >
                            {showSystemTools && (
                                <div className="overflow-y-auto max-h-[400px]">
                                    {/* Settings Tab Buttons */}
                                    <div className="flex border-b dark:border-gray-700">
                                        <button
                                            onClick={() => setShowDataSourcesModal(true)}
                                            className="flex-1 px-3 py-2 text-xs font-medium text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors border-r dark:border-gray-700"
                                        >
                                            📁 資料來源
                                        </button>
                                        <button
                                            onClick={() => setShowRuntimeModal(true)}
                                            className="flex-1 px-3 py-2 text-xs font-medium text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors border-r dark:border-gray-700"
                                        >
                                            ☁️ Runtime
                                        </button>
                                        <button
                                            onClick={() => setShowInstructionModal(true)}
                                            className="flex-1 px-3 py-2 text-xs font-medium text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                                        >
                                            🎯 指令
                                        </button>
                                    </div>

                                    {/* System Status Section */}
                                    <div className="p-3">
                                        {systemStatus ? (
                                            <IntegratedSystemStatusCard
                                                systemStatus={systemStatus}
                                                workspace={workspace || {}}
                                                workspaceId={workspaceId}
                                                onRefresh={onRefreshAll}
                                            />
                                        ) : (
                                            <div className="text-sm text-secondary dark:text-gray-400">Loading system status...</div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Settings Modals */}
            {workspace && (
                <>
                    <StoragePathConfigModal
                        isOpen={showDataSourcesModal}
                        onClose={() => setShowDataSourcesModal(false)}
                        workspace={workspace as any}
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        toolConnections={systemStatus?.tools}
                        onSuccess={() => {
                            window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                        }}
                    />
                    <RuntimeSettingsModal
                        isOpen={showRuntimeModal}
                        onClose={() => setShowRuntimeModal(false)}
                        workspaceId={workspaceId}
                    />
                    <WorkspaceInstructionModal
                        isOpen={showInstructionModal}
                        onClose={() => setShowInstructionModal(false)}
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        initialInstruction={workspace?.workspace_blueprint?.instruction}
                        onUpdate={() => {
                            onRefreshAll();
                        }}
                    />
                </>
            )}
        </div>
    );
}
