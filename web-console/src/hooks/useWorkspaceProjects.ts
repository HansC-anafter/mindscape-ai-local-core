'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { Project } from '@/types/project';
import { getApiBaseUrl } from '@/lib/api-url';
import { Workspace } from '@/app/workspaces/[workspaceId]/workspace-page.types';

const API_URL = getApiBaseUrl();

interface UseWorkspaceProjectsReturn {
    projects: Project[];
    currentProject: Project | null;
    selectedProjectId: string | null;
    selectedType: string | null;
    isLoadingProject: boolean;
    isLoadingProjects: boolean;
    setSelectedProjectId: (id: string | null) => void;
    setSelectedType: (type: string | null) => void;
    setCurrentProject: (project: Project | null) => void;
}

/**
 * Manages project list loading and current project selection for a workspace.
 * Extracted from WorkspacePageContent to reduce page.tsx complexity.
 */
export function useWorkspaceProjects(
    workspaceId: string,
    workspace: Workspace | null
): UseWorkspaceProjectsReturn {
    const searchParams = useSearchParams();

    const [currentProject, setCurrentProject] = useState<Project | null>(null);
    const [isLoadingProject, setIsLoadingProject] = useState(false);
    const [projects, setProjects] = useState<Project[]>([]);
    const [isLoadingProjects, setIsLoadingProjects] = useState(false);
    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
    const [selectedType, setSelectedType] = useState<string | null>(null);

    // Load projects list
    useEffect(() => {
        const loadProjects = async () => {
            setIsLoadingProjects(true);
            try {
                const url = new URL(`${API_URL}/api/v1/workspaces/${workspaceId}/projects`);
                url.searchParams.set('state', 'open');
                url.searchParams.set('limit', '20');
                if (selectedType) {
                    url.searchParams.set('project_type', selectedType);
                }

                const response = await fetch(url.toString());
                if (response.ok) {
                    const data = await response.json();
                    setProjects(data.projects || []);

                    // Set selected project
                    const urlProjectId = searchParams?.get('project_id');
                    if (urlProjectId) {
                        setSelectedProjectId(urlProjectId);
                    } else if (workspace?.primary_project_id) {
                        setSelectedProjectId(workspace.primary_project_id);
                    } else if (data.projects && data.projects.length > 0) {
                        setSelectedProjectId(data.projects[0].id);
                    }
                }
            } catch (err) {
                console.error('[WorkspacePage] Failed to load projects:', err);
                setProjects([]);
            } finally {
                setIsLoadingProjects(false);
            }
        };

        loadProjects();
    }, [workspaceId, workspace?.primary_project_id, selectedType]);

    // Load current project when workspace.primary_project_id or selectedProjectId changes
    useEffect(() => {
        const projectIdToLoad = selectedProjectId || workspace?.primary_project_id;

        console.log('[WorkspacePage] Workspace data:', {
            workspace_id: workspace?.id,
            primary_project_id: workspace?.primary_project_id,
            selected_project_id: selectedProjectId,
            project_id_to_load: projectIdToLoad,
            has_workspace: !!workspace
        });

        if (!projectIdToLoad) {
            console.log('[WorkspacePage] No project ID to load, setting currentProject to null');
            setCurrentProject(null);
            return;
        }

        const loadProject = async () => {
            setIsLoadingProject(true);
            try {
                console.log('[WorkspacePage] Loading project:', {
                    workspaceId,
                    project_id: projectIdToLoad
                });
                const response = await fetch(
                    `${API_URL}/api/v1/workspaces/${workspaceId}/projects/${projectIdToLoad}`
                );
                if (response.ok) {
                    const projectData = await response.json();
                    console.log('[WorkspacePage] Project loaded:', {
                        project_id: projectData.id,
                        project_title: projectData.title,
                        project_type: projectData.type,
                        full_data: projectData
                    });
                    setCurrentProject(projectData);
                } else {
                    // If project not found, try to get first active project from list
                    if (projects && projects.length > 0) {
                        setCurrentProject(projects[0]);
                        setSelectedProjectId(projects[0].id);
                    } else {
                        setCurrentProject(null);
                    }
                }
            } catch (err) {
                console.error('Failed to load project:', err);
                setCurrentProject(null);
            } finally {
                setIsLoadingProject(false);
            }
        };

        loadProject();
    }, [selectedProjectId, workspace?.primary_project_id, workspaceId, projects]);

    // Debug: Log currentProject changes
    useEffect(() => {
        if (process.env.NODE_ENV === 'development') {
            console.log('[WorkspacePage] currentProject changed:', {
                currentProject_id: currentProject?.id,
                currentProject_title: currentProject?.title,
                has_currentProject: !!currentProject,
                workspace_primary_project_id: workspace?.primary_project_id,
                isLoadingProject
            });
        }
    }, [currentProject, workspace?.primary_project_id, isLoadingProject]);

    return {
        projects,
        currentProject,
        selectedProjectId,
        selectedType,
        isLoadingProject,
        isLoadingProjects,
        setSelectedProjectId,
        setSelectedType,
        setCurrentProject,
    };
}
