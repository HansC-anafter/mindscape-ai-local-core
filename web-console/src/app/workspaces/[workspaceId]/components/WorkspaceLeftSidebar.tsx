'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import LeftSidebarTabs from './LeftSidebarTabs';
import ProjectSubTabs from './ProjectSubTabs';
import type { Project } from '@/types/project';

const TimelinePanel = dynamic(() => import('../../components/TimelinePanel'), { ssr: false });

interface WorkspaceLeftSidebarProps {
    workspaceId: string;
    apiUrl: string;
    projects: Project[];
    selectedProjectId: string | null;
    selectedType: string | null;
    isLoadingProject: boolean;
    leftSidebarTab: 'timeline' | 'outcomes';
    setLeftSidebarTab: (tab: 'timeline' | 'outcomes') => void;
    setSelectedType: (type: string | null) => void;
    onProjectSelect: (project: Project) => void;
}

export default function WorkspaceLeftSidebar({
    workspaceId,
    apiUrl,
    projects,
    selectedProjectId,
    selectedType,
    isLoadingProject,
    leftSidebarTab,
    setLeftSidebarTab,
    setSelectedType,
    onProjectSelect,
}: WorkspaceLeftSidebarProps) {
    const router = useRouter();

    return (
        <div className="w-80 border-r dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
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
                                    workspaceId={workspaceId}
                                    apiUrl={apiUrl}
                                    onOpenExecution={(executionId) => {
                                        const executionUrl = `/workspaces/${workspaceId}/executions/${executionId}`;
                                        router.push(executionUrl);
                                    }}
                                />
                            )}

                            {projects.length === 0 && !isLoadingProject && (
                                <div className="px-3 py-2">
                                    <div className="project-placeholder text-center py-8">
                                        <div className="text-sm font-medium text-primary dark:text-gray-300 mb-1">
                                            No Active Projects
                                        </div>
                                        <div className="text-xs text-secondary dark:text-gray-400">
                                            Projects will be created automatically after the conversation starts.
                                        </div>
                                    </div>
                                </div>
                            )}
                            {isLoadingProject && projects.length === 0 && (
                                <div className="text-xs text-secondary dark:text-gray-400 p-3">
                                    Loading...
                                </div>
                            )}
                        </div>
                    }
                    outcomesContent={
                        leftSidebarTab === 'outcomes' ? (
                            <TimelinePanel
                                workspaceId={workspaceId}
                                apiUrl={apiUrl}
                                isInSettingsPage={false}
                                showArchivedOnly={true}
                            />
                        ) : null
                    }
                />
            </div>
        </div>
    );
}
