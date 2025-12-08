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
  const { projects, activeProjects, closedProjects, refreshProjects, isLoadingProjects } = useWorkspaceData();
  const [showClosed, setShowClosed] = useState(false);

  useEffect(() => {
    refreshProjects();
  }, [workspaceId, refreshProjects]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
        <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          Projects ({activeProjects.length})
        </div>
        {closedProjects.length > 0 && (
          <button
            onClick={() => setShowClosed(!showClosed)}
            className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            {showClosed ? 'Hide' : 'Show'} Closed ({closedProjects.length})
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {isLoadingProjects ? (
          <div className="text-xs text-gray-500 dark:text-gray-400">Loading...</div>
        ) : (
          <>
            {activeProjects.length === 0 ? (
              <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-8">
                No active projects
              </div>
            ) : (
              activeProjects.map(project => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onClick={() => onProjectSelect?.(project)}
                />
              ))
            )}

            {showClosed && closedProjects.length > 0 && (
              <>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-4 mb-2">
                  Closed ({closedProjects.length})
                </div>
                {closedProjects.map(project => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    onClick={() => onProjectSelect?.(project)}
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


