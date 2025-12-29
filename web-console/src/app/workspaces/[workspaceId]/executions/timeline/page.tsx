'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';

import { getApiBaseUrl } from '../../../../../lib/api-url';

const API_URL = getApiBaseUrl();

interface Execution {
  id: string;
  workspace_id: string;
  playbook_code: string;
  playbook_version?: string;
  status: string;
  storyline_tags?: string[];
  origin_intent_id?: string;
  origin_intent_label?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  steps?: any[];
}

export default function ExecutionTimelinePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();
  const { workspace } = useWorkspaceData();
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);

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

  const getStatusColor = (status: string): string => {
    const colors: Record<string, string> = {
      done: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      running: 'bg-accent-10 text-accent dark:bg-blue-900 dark:text-blue-200',
      paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
    };
    return colors[status] || 'bg-surface-secondary text-primary';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-secondary">Loading execution timeline...</div>
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

  // Sort executions by created_at (newest first)
  const sortedExecutions = [...executions].sort((a, b) => {
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
        <h1 className="text-2xl font-bold text-primary dark:text-gray-100">
          Execution Timeline
        </h1>
        <p className="text-sm text-secondary dark:text-gray-400 mt-1">
          Trace execution history and decision chains
        </p>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex">
        {/* Timeline */}
        <div className="flex-1 overflow-y-auto p-6">
          {sortedExecutions.length === 0 ? (
            <div className="text-center py-12 text-secondary">
              No executions yet
            </div>
          ) : (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-default dark:bg-gray-700"></div>

              {/* Execution items */}
              <div className="space-y-6">
                {sortedExecutions.map((execution, index) => (
                  <div
                    key={execution.id}
                    className="relative flex items-start gap-4 cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-800 p-4 rounded-lg transition-colors"
                    onClick={() => setSelectedExecution(execution)}
                  >
                    {/* Timeline dot */}
                    <div className="relative z-10 w-4 h-4 rounded-full bg-accent dark:bg-blue-500 border-2 border-surface-accent dark:border-gray-900"></div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold text-primary dark:text-gray-100">
                              {execution.playbook_code}
                            </h3>
                            {execution.playbook_version && (
                              <span className="text-xs text-secondary dark:text-gray-500">
                                v{execution.playbook_version}
                              </span>
                            )}
                            <span className={`text-xs px-2 py-1 rounded ${getStatusColor(execution.status)}`}>
                              {execution.status}
                            </span>
                          </div>

                          {execution.origin_intent_label && (
                            <div className="text-sm text-secondary dark:text-gray-400 mb-2">
                              From Intent: {execution.origin_intent_label}
                            </div>
                          )}

                          {execution.storyline_tags && execution.storyline_tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mb-2">
                              {execution.storyline_tags.map(tag => (
                                <span
                                  key={tag}
                                  className="text-xs px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 rounded"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}

                          <div className="text-xs text-secondary dark:text-gray-500">
                            {new Date(execution.created_at).toLocaleString()}
                            {execution.completed_at && (
                              <span className="ml-2">
                                • Completed: {new Date(execution.completed_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/workspaces/${workspaceId}/executions/${execution.id}`);
                          }}
                          className="px-3 py-1 text-sm bg-accent dark:bg-blue-600 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-700 transition-colors"
                        >
                          View Details
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Detail Panel */}
        {selectedExecution && (
          <div className="w-96 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 overflow-y-auto">
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                  Execution Details
                </h2>
                <button
                  onClick={() => setSelectedExecution(null)}
                  className="text-secondary hover:text-primary dark:hover:text-gray-300"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-secondary dark:text-gray-400">
                    Playbook
                  </label>
                  <div className="text-sm text-primary dark:text-gray-100 mt-1">
                    {selectedExecution.playbook_code}
                    {selectedExecution.playbook_version && (
                      <span className="text-secondary ml-2">v{selectedExecution.playbook_version}</span>
                    )}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Status
                  </label>
                  <div className="mt-1">
                    <span className={`text-xs px-2 py-1 rounded ${getStatusColor(selectedExecution.status)}`}>
                      {selectedExecution.status}
                    </span>
                  </div>
                </div>

                {selectedExecution.origin_intent_label && (
                  <div>
                    <label className="text-xs font-medium text-secondary dark:text-gray-400">
                      Origin Intent
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                      {selectedExecution.origin_intent_label}
                    </div>
                  </div>
                )}

                {selectedExecution.storyline_tags && selectedExecution.storyline_tags.length > 0 && (
                  <div>
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      Storyline Tags
                    </label>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {selectedExecution.storyline_tags.map(tag => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-xs font-medium text-secondary dark:text-gray-400">
                    Created
                  </label>
                  <div className="text-sm text-primary dark:text-gray-100 mt-1">
                    {new Date(selectedExecution.created_at).toLocaleString()}
                  </div>
                </div>

                {selectedExecution.completed_at && (
                  <div>
                    <label className="text-xs font-medium text-secondary dark:text-gray-400">
                      Completed
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                      {new Date(selectedExecution.completed_at).toLocaleString()}
                    </div>
                  </div>
                )}

                <button
                  onClick={() => router.push(`/workspaces/${workspaceId}/executions/${selectedExecution.id}`)}
                  className="w-full px-4 py-2 bg-accent dark:bg-blue-600 text-white rounded-lg hover:bg-accent/90 dark:hover:bg-blue-700 transition-colors"
                >
                  View Full Details
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
