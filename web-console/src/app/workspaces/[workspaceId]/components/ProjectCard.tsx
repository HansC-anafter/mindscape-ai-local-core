'use client';

import React from 'react';
import { Project } from '@/types/project';

interface ProjectCardProps {
  project: Project;
  onClick?: () => void;
}

export default function ProjectCard({ project, onClick }: ProjectCardProps) {
  const getTypeIcon = (type: string) => {
    const icons: Record<string, string> = {
      web_page: '🌐',
      book: '📚',
      course: '🎓',
      campaign: '📢',
      video_series: '🎬'
    };
    return icons[type] || '📦';
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case 'open':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
      case 'closed':
        return 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400';
      case 'archived':
        return 'bg-gray-50 dark:bg-gray-900 text-gray-400 dark:text-gray-600';
      default:
        return 'bg-gray-100';
    }
  };

  const getStateLabel = (state: string) => {
    switch (state) {
      case 'open':
        return 'Open';
      case 'closed':
        return 'Closed';
      case 'archived':
        return 'Archived';
      default:
        return state;
    }
  };

  return (
    <div
      onClick={onClick}
      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 cursor-pointer hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-lg flex-shrink-0">{getTypeIcon(project.type)}</span>
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {project.title}
          </h3>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${getStateColor(project.state)}`}>
          {getStateLabel(project.state)}
        </span>
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
        <div>Type: {project.type}</div>
        {project.human_owner_user_id && (
          <div>Owner: {project.human_owner_user_id}</div>
        )}
        <div className="text-[10px]">
          Updated: {new Date(project.updated_at).toLocaleDateString()}
        </div>
      </div>
    </div>
  );
}


