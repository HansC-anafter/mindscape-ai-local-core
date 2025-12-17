'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Execution {
  id: string;
  workspace_id: string;
  playbook_code: string;
  status: string;
  storyline_tags?: string[];
  created_at: string;
  completed_at?: string;
}

export default function StorylineOverviewPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const { workspace } = useWorkspaceData();
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStoryline, setSelectedStoryline] = useState<string | null>(null);

  useEffect(() => {
    const loadExecutions = async () => {
      try {
        setLoading(true);
        setError(null);

        // Load all executions for this workspace
        const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/executions-with-steps?limit=100`);
        if (!response.ok) {
          throw new Error(`Failed to load executions: ${response.statusText}`);
        }
        const data = await response.json();
        setExecutions(data.executions || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load executions');
      } finally {
        setLoading(false);
      }
    };

    loadExecutions();
  }, [workspaceId]);

  // Extract unique storyline tags
  const storylineTags = Array.from(
    new Set(
      executions
        .flatMap(e => e.storyline_tags || [])
        .filter(Boolean)
    )
  ).sort();

  // Group executions by storyline
  const executionsByStoryline = storylineTags.reduce((acc, tag) => {
    acc[tag] = executions.filter(e => e.storyline_tags?.includes(tag));
    return acc;
  }, {} as Record<string, Execution[]>);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">Loading storylines...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b dark:border-gray-700 bg-white dark:bg-gray-900">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Storyline Overview
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Visualize and track storylines across projects
        </p>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex">
        {/* Storyline List Sidebar */}
        <div className="w-64 border-r dark:border-gray-700 bg-gray-50 dark:bg-gray-800 overflow-y-auto">
          <div className="p-4">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Storylines ({storylineTags.length})
            </h2>
            {storylineTags.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                No storylines yet. Add storyline tags to intents to see them here.
              </div>
            ) : (
              <div className="space-y-2">
                {storylineTags.map(tag => (
                  <button
                    key={tag}
                    onClick={() => setSelectedStoryline(tag)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                      selectedStoryline === tag
                        ? 'bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-200'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <div className="font-medium">{tag}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      {executionsByStoryline[tag]?.length || 0} executions
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Execution List */}
        <div className="flex-1 overflow-y-auto p-6">
          {selectedStoryline ? (
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {selectedStoryline}
              </h2>
              {executionsByStoryline[selectedStoryline]?.length === 0 ? (
                <div className="text-gray-500 text-center py-8">
                  No executions for this storyline yet
                </div>
              ) : (
                <div className="space-y-4">
                  {executionsByStoryline[selectedStoryline]?.map(execution => (
                    <div
                      key={execution.id}
                      className="border rounded-lg p-4 bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {execution.playbook_code}
                          </div>
                          <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            {execution.status} • {new Date(execution.created_at).toLocaleDateString()}
                          </div>
                        </div>
                        <span className={`text-xs px-2 py-1 rounded ${
                          execution.status === 'done' ? 'bg-green-100 text-green-800' :
                          execution.status === 'running' ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {execution.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Select a storyline from the sidebar to view executions
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
