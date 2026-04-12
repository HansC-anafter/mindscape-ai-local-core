'use client';

/**
 * Series Panel
 *
 * Features:
 * - Series list view
 * - Series detail panel
 * - Series progress tracking
 * - Post navigation within series
 */

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { BookOpen, Plus, Search, List, BarChart3, ChevronRight } from 'lucide-react';
import type { IGPost } from '../types';

interface SeriesPanelProps {
  workspaceId: string;
  apiUrl: string;
  selectedPostId: string | null;
  posts: IGPost[];
  onPostSelect: (postId: string) => void;
}

interface Series {
  series_code: string;
  series_name: string;
  description?: string;
  total_posts?: number;
  current_posts?: number;
  posts?: Array<{
    post_path: string;
    post_slug: string;
    post_number: number;
  }>;
}

export default function SeriesPanel({
  workspaceId,
  apiUrl,
  selectedPostId,
  posts,
  onPostSelect
}: SeriesPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [selectedSeries, setSelectedSeries] = useState<Series | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadSeriesList();
  }, [workspaceId, apiUrl]);

  const loadSeriesList = async () => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_series_manager',
        inputs: {
          action: 'list',
          workspace_id: workspaceId
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        const series = data.result?.series_list || [];
        setSeriesList(series);
      }
    } catch (err) {
      console.error('Failed to load series list:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSeries = async () => {
    // TODO: Open create series dialog
    alert('Create series feature (to be implemented in Phase 2)');
  };

  const handleSelectSeries = async (seriesCode: string) => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_series_manager',
        inputs: {
          action: 'get',
          workspace_id: workspaceId,
          series_code: seriesCode
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        const series = data.result?.series;
        if (series) {
          const postsResponse = await client.post('/api/v1/playbooks/execute', {
            playbook_code: 'ig_series_manager',
            inputs: {
              action: 'get_posts',
              workspace_id: workspaceId,
              series_code: seriesCode
            },
            execution_mode: 'sync'
          });

          if (postsResponse.ok) {
            const postsData = await postsResponse.json();
            series.posts = postsData.result?.posts || [];
          }

          setSelectedSeries(series);
        }
      }
    } catch (err) {
      console.error('Failed to load series:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredSeries = seriesList.filter(series =>
    series.series_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    series.series_code.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (selectedSeries) {
    const progress = selectedSeries.total_posts && selectedSeries.current_posts
      ? (selectedSeries.current_posts / selectedSeries.total_posts) * 100
      : 0;

    return (
      <div className="h-full flex flex-col p-4">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => setSelectedSeries(null)}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            Back to Series List
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
              {selectedSeries.series_name}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {selectedSeries.series_code}
            </p>
            {selectedSeries.description && (
              <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
                {selectedSeries.description}
              </p>
            )}
          </div>

          {/* Progress tracking */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Progress Tracking
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {selectedSeries.current_posts || 0} / {selectedSeries.total_posts || '?'} posts
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Posts in series */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
              Posts in Series
            </h3>
            <div className="space-y-2">
              {selectedSeries.posts && selectedSeries.posts.length > 0 ? (
                selectedSeries.posts.map((post, index) => {
                  const matchingPost = posts.find(p => p.post_path === post.post_path);
                  return (
                    <div
                      key={index}
                      onClick={() => matchingPost && onPostSelect(matchingPost.id)}
                      className={`p-3 rounded-lg border cursor-pointer transition-colors ${matchingPost && selectedPostId === matchingPost.id
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600'
                        }`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            #{post.post_number}
                          </span>
                          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 ml-2">
                            {post.post_slug || post.post_path}
                          </span>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      </div>
                    </div>
                  );
                })
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                  No posts
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          Series Management
        </h2>
        <button
          onClick={handleCreateSeries}
          className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus className="w-3.5 h-3.5" />
          New Series
        </button>
      </div>

      {/* Search box */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search series..."
            className="w-full pl-10 pr-4 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Series list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            Loading series...
          </div>
        ) : filteredSeries.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            {searchQuery ? 'No matching series found' : 'No series. Click "New Series" to create'}
          </div>
        ) : (
          filteredSeries.map((series) => {
            const progress = series.total_posts && series.current_posts
              ? (series.current_posts / series.total_posts) * 100
              : 0;

            return (
              <div
                key={series.series_code}
                onClick={() => handleSelectSeries(series.series_code)}
                className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      {series.series_name}
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {series.series_code}
                    </p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                </div>

                {series.description && (
                  <p className="text-xs text-gray-600 dark:text-gray-300 mb-2 truncate">
                    {series.description}
                  </p>
                )}

                {/* Progress bar */}
                <div className="mt-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      Progress
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {series.current_posts || 0} / {series.total_posts || '?'}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                    <div
                      className="bg-blue-600 h-1.5 rounded-full transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
