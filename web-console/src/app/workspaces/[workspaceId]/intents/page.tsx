'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import Link from 'next/link';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

interface Intent {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  tags: string[];
  storyline_tags?: string[];
  created_at: string;
  updated_at: string;
}

export default function IntentPoolPage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const router = useRouter();
  const { workspace } = useWorkspaceData();
  const [intents, setIntents] = useState<Intent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newIntent, setNewIntent] = useState({
    title: '',
    description: '',
    storyline_tags: [] as string[]
  });

  useEffect(() => {
    const loadIntents = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/intents`);
        if (!response.ok) {
          throw new Error(`Failed to load intents: ${response.statusText}`);
        }
        const data = await response.json();
        setIntents(data.intents || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load intents');
      } finally {
        setLoading(false);
      }
    };

    loadIntents();
  }, [workspaceId]);

  const handleCreateIntent = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/intents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId,
          title: newIntent.title,
          description: newIntent.description,
          storyline_tags: newIntent.storyline_tags,
          status: 'CONFIRMED'
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create intent');
      }

      // Reload intents
      const loadResponse = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/intents`);
      const data = await loadResponse.json();
      setIntents(data.intents || []);

      // Reset form
      setNewIntent({ title: '', description: '', storyline_tags: [] });
      setShowCreateForm(false);
    } catch (e) {
      alert('Failed to create intent: ' + (e instanceof Error ? e.message : 'Unknown error'));
    }
  };

  const getStatusColor = (status: string): string => {
    const colors: Record<string, string> = {
      ACTIVE: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      PAUSED: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      ARCHIVED: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">Loading intents...</div>
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
      <div className="px-6 py-4 border-b dark:border-gray-700 bg-white dark:bg-gray-900 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Intent Pool
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Manage and track all intents for this workspace
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          {showCreateForm ? 'Cancel' : '+ New Intent'}
        </button>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="px-6 py-4 border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <form onSubmit={handleCreateIntent} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Title
              </label>
              <input
                type="text"
                value={newIntent.title}
                onChange={(e) => setNewIntent({ ...newIntent, title: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Description
              </label>
              <textarea
                value={newIntent.description}
                onChange={(e) => setNewIntent({ ...newIntent, description: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                rows={3}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Storyline Tags (comma-separated)
              </label>
              <input
                type="text"
                value={newIntent.storyline_tags.join(', ')}
                onChange={(e) => setNewIntent({
                  ...newIntent,
                  storyline_tags: e.target.value.split(',').map(t => t.trim()).filter(t => t)
                })}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                placeholder="e.g., story-arc-1, rebranding"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Create Intent
            </button>
          </form>
        </div>
      )}

      {/* Intent Cards Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {intents.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No intents yet. Create your first intent to get started.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {intents.map(intent => (
              <div
                key={intent.id}
                className="border rounded-lg p-4 hover:shadow-md transition-shadow bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 cursor-pointer"
                onClick={() => router.push(`/workspaces/${workspaceId}/intents/${intent.id}`)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 flex-1">
                    {intent.title}
                  </h3>
                  <span className={`text-xs px-2 py-1 rounded ${getStatusColor(intent.status)}`}>
                    {intent.status}
                  </span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
                  {intent.description}
                </p>
                {intent.storyline_tags && intent.storyline_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2">
                    {intent.storyline_tags.map(tag => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                {intent.tags && intent.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {intent.tags.map(tag => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-1 bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
