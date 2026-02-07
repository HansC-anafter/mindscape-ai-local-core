'use client';

import React, { useState, useEffect } from 'react';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import ProjectCard from './ProjectCard';
import { Project } from '@/types/project';

interface ProjectsPanelProps {
  workspaceId: string;
  apiUrl: string;
  onProjectSelect?: (project: Project) => void;
}

export default function ProjectsPanel({
  workspaceId,
  apiUrl,
  onProjectSelect
}: ProjectsPanelProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [showClosed, setShowClosed] = useState(false);

  // Provide safe defaults for projects arrays
  const safeActiveProjects = projects.filter(p => p.state === 'open') || [];
  const safeClosedProjects = projects.filter(p => p.state === 'closed' || p.state === 'archived') || [];

  const refreshProjects = async () => {
    setIsLoadingProjects(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects`);
      if (!response.ok) {
        throw new Error(`Failed to fetch projects: ${response.status}`);
      }
      const data = await response.json();
      setProjects(data.projects || []);
    } catch (error) {
      console.error('Failed to load projects:', error);
      setProjects([]);
    } finally {
      setIsLoadingProjects(false);
    }
  };

  useEffect(() => {
    refreshProjects();
  }, [workspaceId, apiUrl]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
        <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          Projects ({safeActiveProjects.length})
        </div>
        {safeClosedProjects.length > 0 && (
          <button
            onClick={() => setShowClosed(!showClosed)}
            className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            {showClosed ? 'Hide' : 'Show'} Closed ({safeClosedProjects.length})
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {isLoadingProjects ? (
          <div className="text-xs text-gray-500 dark:text-gray-400">Loading...</div>
        ) : (
          <>
            {safeActiveProjects.length === 0 ? (
              <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-8">
                No active projects
              </div>
            ) : (
              safeActiveProjects.map(project => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onFocus={() => onProjectSelect?.(project)}
                />
              ))
            )}

            {showClosed && safeClosedProjects.length > 0 && (
              <>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-4 mb-2">
                  Closed ({safeClosedProjects.length})
                </div>
                {safeClosedProjects.map(project => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    onFocus={() => onProjectSelect?.(project)}
                  />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}









