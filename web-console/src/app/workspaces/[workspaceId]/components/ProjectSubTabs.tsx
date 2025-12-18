'use client';

import React, { useState } from 'react';
import { Project } from '@/types/project';
import { t } from '@/lib/i18n';

interface ProjectSubTabsProps {
  projects: Project[];
  selectedType: string | null;
  selectedProjectId: string | null;
  onTypeChange: (type: string | null) => void;
  onProjectSelect: (project: Project) => void;
}

type SubTab = 'list' | 'categories';

export default function ProjectSubTabs({
  projects,
  selectedType,
  selectedProjectId,
  onTypeChange,
  onProjectSelect,
}: ProjectSubTabsProps) {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('list');

  const projectTypes = Array.from(new Set(projects.map(p => p.type || 'other')));
  const hasMultipleTypes = projectTypes.length > 1;
  const filteredProjects = selectedType
    ? projects.filter(p => (p.type || 'other') === selectedType)
    : projects;

  return (
    <div className="flex-shrink-0 border-b dark:border-gray-700">
      <div className="flex items-center gap-1 px-2 pt-2 pb-1 border-b dark:border-gray-700">
        <button
          onClick={() => setActiveSubTab('list')}
          className={`p-1.5 rounded transition-colors ${
            activeSubTab === 'list'
              ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
              : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
          title={t('projectList') || 'Project List'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
            />
          </svg>
        </button>
        {hasMultipleTypes && (
          <button
            onClick={() => setActiveSubTab('categories')}
            className={`p-1.5 rounded transition-colors ${
              activeSubTab === 'categories'
                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
            title={t('projectCategories') || 'Project Categories'}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
              />
            </svg>
          </button>
        )}
      </div>

      <div className="px-3 py-2">
        {activeSubTab === 'list' && (
          <div>
            <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              {t('projectList') || 'Project List'} ({filteredProjects.length})
            </div>
            {filteredProjects.length > 0 ? (
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {filteredProjects.map(project => (
                  <button
                    key={project.id}
                    onClick={() => onProjectSelect(project)}
                    className={`w-full text-left px-2 py-1.5 text-xs rounded transition-colors ${
                      selectedProjectId === project.id
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <div className="truncate font-medium">{project.title}</div>
                    <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                      {project.type || 'general'} • {project.state || 'open'}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500 dark:text-gray-400 py-2">
                {t('noProjects') || 'No projects'}
              </div>
            )}
          </div>
        )}

        {activeSubTab === 'categories' && hasMultipleTypes && (
          <div>
            <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              {t('projectCategories') || 'Project Categories'}
            </div>
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => onTypeChange(null)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  selectedType === null
                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
              >
                {t('all') || 'All'} ({projects.length})
              </button>
              {projectTypes.map(type => {
                const count = projects.filter(p => (p.type || 'other') === type).length;
                return (
                  <button
                    key={type}
                    onClick={() => onTypeChange(type)}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      selectedType === type
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {type} ({count})
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

