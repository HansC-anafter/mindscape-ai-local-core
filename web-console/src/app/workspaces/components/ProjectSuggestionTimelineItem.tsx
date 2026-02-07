'use client';

import React, { useState } from 'react';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import { ProjectSuggestion } from '@/types/project';

interface TimelineItem {
  id: string;
  workspace_id: string;
  type: string;
  title: string;
  summary?: string;
  data?: any;
  created_at: string;
}

interface ProjectSuggestionTimelineItemProps {
  item: TimelineItem;
  apiUrl: string;
  workspaceId: string;
  onProjectCreated?: (projectId: string) => void;
}

export default function ProjectSuggestionTimelineItem({
  item,
  apiUrl,
  workspaceId,
  onProjectCreated
}: ProjectSuggestionTimelineItemProps) {
  const [creating, setCreating] = useState(false);
  const workspaceData = useWorkspaceData() as any;
  const { createProject, refreshProjects } = workspaceData;
  const suggestion = item.data?.suggestion as ProjectSuggestion | undefined;

  const handleAccept = async () => {
    if (!suggestion) return;

    setCreating(true);
    try {
      const project = await createProject(suggestion);
      if (project) {
        onProjectCreated?.(project.id);
        window.dispatchEvent(new Event('workspace-chat-updated'));
      }
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDismiss = () => {
    // TODO: Mark suggestion as dismissed (can be implemented via API or local state)
  };

  if (!suggestion) {
    return null;
  }

  return (
    <div className="bg-purple-50 dark:bg-purple-900/10 border border-purple-200 dark:border-purple-800 rounded-lg p-3 mb-2">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-purple-600 dark:text-purple-400">💡</span>
        <span className="text-xs font-medium text-purple-900 dark:text-purple-100">
          This sounds like a new project
        </span>
      </div>

      {suggestion && (
        <div className="mb-3">
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {suggestion.project_title}
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400">
            Type: {suggestion.project_type}
          </div>
          {suggestion.initial_spec_md && (
            <div className="text-xs text-gray-500 dark:text-gray-500 mt-1 line-clamp-2">
              {suggestion.initial_spec_md.substring(0, 150)}...
            </div>
          )}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleAccept}
          disabled={creating}
          className="flex-1 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {creating ? 'Creating...' : 'Create Project'}
        </button>
        <button
          onClick={handleDismiss}
          className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 text-xs rounded"
        >
          Later
        </button>
      </div>
    </div>
  );
}



















