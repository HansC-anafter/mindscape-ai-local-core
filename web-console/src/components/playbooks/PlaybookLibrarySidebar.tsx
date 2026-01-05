'use client';

import React, { useState, useMemo } from 'react';
import { t, useLocale } from '../../lib/i18n';

interface Playbook {
  playbook_code: string;
  name: string;
  description: string;
  icon?: string;
  tags: string[];
  user_meta: {
    favorite: boolean;
    use_count: number;
  };
  workspace_usage_count?: number;
  pinned_workspaces?: Array<{
    id: string;
    title: string;
  }>;
  required_tools: string[];
  capability_code?: string;
}

interface PlaybookLibrarySidebarProps {
  playbooks: Playbook[];
  selectedTags: string[];
  onTagsChange: (tags: string[]) => void;
  selectedWorkspaceId: string | null;
  onWorkspaceChange: (workspaceId: string | null) => void;
  selectedCapability: string;
  onCapabilityChange: (capability: string) => void;
  playbooksByCapability: Record<string, Playbook[]>;
  filter?: string;
  onFilterChange?: (filter: string | null) => void;
  profileId?: string;
}

export default function PlaybookLibrarySidebar({
  playbooks,
  selectedTags,
  onTagsChange,
  selectedWorkspaceId,
  onWorkspaceChange,
  selectedCapability,
  onCapabilityChange,
  playbooksByCapability,
  filter,
  onFilterChange,
  profileId = 'default-user'
}: PlaybookLibrarySidebarProps) {
  const [locale] = useLocale();
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [tagSearchTerm, setTagSearchTerm] = useState('');
  const [showAllTags, setShowAllTags] = useState(false);

  // Calculate tag frequency for Top 12
  const allTags = useMemo(() => {
    return Array.from(
      new Set(playbooks.flatMap(p => p.tags || []))
    ).sort();
  }, [playbooks]);

  const topTags = useMemo(() => {
    const tagCounts: Record<string, number> = {};
    playbooks.forEach(p => {
      (p.tags || []).forEach(tag => {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      });
    });
    return Object.entries(tagCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 12)
      .map(([tag]) => tag);
  }, [playbooks]);

  // Filter tags based on search and showAllTags
  const displayedTags = useMemo(() => {
    let tagsToShow = showAllTags ? allTags : topTags;

    if (tagSearchTerm.trim()) {
      const lowerSearch = tagSearchTerm.toLowerCase();
      tagsToShow = tagsToShow.filter(tag =>
        tag.toLowerCase().includes(lowerSearch)
      );
    }

    return tagsToShow;
  }, [allTags, topTags, tagSearchTerm, showAllTags]);

  // Get favorite playbook codes
  const favoritePlaybookCodes = useMemo(() => {
    return playbooks
      .filter(p => p.user_meta?.favorite)
      .map(p => p.playbook_code);
  }, [playbooks]);

  // Get recent playbook codes (by use_count, top 20)
  const recentPlaybookCodes = useMemo(() => {
    return playbooks
      .filter(p => (p.user_meta?.use_count || 0) > 0)
      .sort((a, b) => (b.user_meta?.use_count || 0) - (a.user_meta?.use_count || 0))
      .slice(0, 20)
      .map(p => p.playbook_code);
  }, [playbooks]);

  // Get ready to run playbooks (all required tools available)
  const readyToRunPlaybookCodes = useMemo(() => {
    // This would need tool registry check - for now, return all
    // In real implementation, check if all required_tools are available
    return playbooks.map(p => p.playbook_code);
  }, [playbooks]);

  // Get workspace-specific playbooks
  const workspacePinnedPlaybookCodes = useMemo(() => {
    if (!selectedWorkspaceId) return [];
    return playbooks
      .filter(p => p.pinned_workspaces?.some(ws => ws.id === selectedWorkspaceId))
      .map(p => p.playbook_code);
  }, [playbooks, selectedWorkspaceId]);

  const workspaceFrequentPlaybookCodes = useMemo(() => {
    if (!selectedWorkspaceId) return [];
    // Playbooks frequently used in this workspace (would need execution history)
    // For now, return playbooks with high workspace_usage_count
    return playbooks
      .filter(p => (p.workspace_usage_count || 0) > 0)
      .sort((a, b) => (b.workspace_usage_count || 0) - (a.workspace_usage_count || 0))
      .slice(0, 10)
      .map(p => p.playbook_code);
  }, [playbooks, selectedWorkspaceId]);

  const handleFilterClick = (filterType: string) => {
    if (onFilterChange) {
      onFilterChange(filter === filterType ? null : filterType);
    }
  };

  return (
    <div className="bg-surface-secondary dark:bg-gray-900 shadow h-[calc(100vh-8rem)] overflow-y-auto p-4 sticky top-0">
      <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">{t('filterTags')}</h3>

      <div className="mb-4">
        <h4 className="text-xs font-semibold text-primary dark:text-gray-300 mb-2">{t('myPlaybooks')}</h4>
        <div className="space-y-1">
          <button
            onClick={() => handleFilterClick('favorites')}
            className={`w-full text-left px-2 py-1.5 text-xs rounded-md transition-colors ${
              filter === 'favorites'
                ? 'bg-accent-10 dark:bg-blue-900/20 text-accent dark:text-blue-300'
                : 'hover:bg-tertiary dark:hover:bg-gray-800 text-primary dark:text-gray-300'
            }`}
          >
            {t('favorites')} ({favoritePlaybookCodes.length})
          </button>
          <button
            onClick={() => handleFilterClick('recent')}
            className={`w-full text-left px-2 py-1.5 text-xs rounded-md transition-colors ${
              filter === 'recent'
                ? 'bg-accent-10 dark:bg-blue-900/20 text-accent dark:text-blue-300'
                : 'hover:bg-tertiary dark:hover:bg-gray-800 text-primary dark:text-gray-300'
            }`}
          >
            {t('recentUsage')} ({recentPlaybookCodes.length})
          </button>
          <button
            onClick={() => {}}
            disabled
            className="w-full text-left px-2 py-1.5 text-xs rounded-md transition-colors opacity-50 cursor-not-allowed text-primary dark:text-gray-300"
            title={t('notYetImplemented')}
          >
            {t('createdByMe')} (0)
          </button>
          <button
            onClick={() => handleFilterClick('ready_to_run')}
            className={`w-full text-left px-2 py-1.5 text-xs rounded-md transition-colors ${
              filter === 'ready_to_run'
                ? 'bg-accent-10 dark:bg-blue-900/20 text-accent dark:text-blue-300'
                : 'hover:bg-tertiary dark:hover:bg-gray-800 text-primary dark:text-gray-300'
            }`}
          >
            {t('readyToRun')} ({readyToRunPlaybookCodes.length})
          </button>
        </div>
      </div>

      <div className="mb-4">
        <h4 className="text-xs font-semibold text-primary dark:text-gray-300 mb-2">{t('byPacks')}</h4>
        <div className="mb-2">
          <select
            value={selectedCapability}
            onChange={(e) => onCapabilityChange(e.target.value)}
            className="w-full px-2 py-1.5 text-xs border border-default dark:border-gray-600 rounded-md bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent dark:focus:ring-blue-500"
          >
            {Object.entries(playbooksByCapability)
              .filter(([_, playbooks]) => playbooks.length > 0)
              .map(([capabilityCode, capabilityPlaybooks]) => {
                const capabilityDisplayName = capabilityCode === 'system'
                  ? t('systemPlaybooks')
                  : capabilityCode.split('_').map(word =>
                      word.charAt(0).toUpperCase() + word.slice(1)
                    ).join(' ');
                return (
                  <option key={capabilityCode} value={capabilityCode}>
                    {capabilityDisplayName} ({capabilityPlaybooks.length})
                  </option>
                );
              })}
          </select>
        </div>
      </div>

      <div className="mb-4">
        <button
          onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
          className="w-full text-left px-2 py-1.5 text-xs font-semibold text-primary dark:text-gray-300 mb-2 flex items-center justify-between"
        >
          <span>{t('advancedFilters')}</span>
          <span>{showAdvancedFilters ? '▼' : '▶'}</span>
        </button>

        {showAdvancedFilters && (
          <div className="space-y-3 pl-2">
            {/* Tags Filter */}
            {allTags.length > 0 && (
              <div>
                <h5 className="text-xs font-medium text-primary dark:text-gray-300 mb-2">{t('tags')}</h5>

                <input
                  type="text"
                  placeholder={t('searchTags')}
                  value={tagSearchTerm}
                  onChange={(e) => setTagSearchTerm(e.target.value)}
                  className="w-full px-2 py-1.5 text-xs border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 mb-2"
                />

                {/* Tag List */}
                {displayedTags.length > 0 ? (
                  <>
                    {displayedTags.map(tag => (
                      <label key={tag} className="flex items-center mb-1.5">
                        <input
                          type="checkbox"
                          checked={selectedTags.includes(tag)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              onTagsChange([...selectedTags, tag]);
                            } else {
                              onTagsChange(selectedTags.filter(t => t !== tag));
                            }
                          }}
                          className="mr-2"
                        />
                        <span className="text-xs text-primary dark:text-gray-300">{tag}</span>
                      </label>
                    ))}

                    {/* Expand/Collapse Button */}
                    {!tagSearchTerm && (
                      <button
                        onClick={() => setShowAllTags(!showAllTags)}
                        className="w-full mt-2 px-2 py-1 text-xs text-accent dark:text-blue-400 hover:bg-accent-10 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                      >
                        {showAllTags
                          ? t('showLess')
                          : t('showMore', { count: allTags.length - topTags.length })
                        }
                      </button>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-secondary dark:text-gray-400 text-center py-2">
                    {t('noTagsFound')}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

