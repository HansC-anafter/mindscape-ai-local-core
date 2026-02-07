'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

interface IntentCard {
  id: string;
  title: string;
  description?: string;
  status: 'active' | 'completed' | 'archived';
  priority: 'high' | 'medium' | 'low';
  progress_percentage?: number;
  created_at?: string;
  updated_at?: string;
  metadata?: {
    source?: string;
    cluster_id?: string;
    cluster_label?: string;
  };
}

interface IntentPanelProps {
  workspaceId: string;
  profileId: string;
  apiUrl: string;
  onClose?: () => void;
}

export default function IntentPanel({
  workspaceId,
  profileId,
  apiUrl,
  onClose
}: IntentPanelProps) {
  const [intentCards, setIntentCards] = useState<IntentCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'active' | 'completed'>('all');
  const [groupBy, setGroupBy] = useState<'none' | 'cluster'>('cluster');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadIntentCards();
  }, [workspaceId, profileId, filter]);

  const loadIntentCards = async () => {
    try {
      setLoading(true);
      setError(null);

      // Try to get intents from profile
      // Note: This endpoint may need to be created if it doesn't exist
      const response = await fetch(
        `${apiUrl}/api/v1/profiles/${profileId}/intents?status=${filter === 'all' ? '' : filter}`
      );

      if (response.ok) {
        const data = await response.json();
        setIntentCards(data.intents || []);
      } else if (response.status === 404) {
        // Endpoint might not exist yet, show empty state
        setIntentCards([]);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        setError(errorData.detail || 'Failed to load intent cards');
      }
    } catch (err: any) {
      console.error('Failed to load intent cards:', err);
      setError(err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
      case 'completed':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
      case 'archived':
        return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'text-red-600 dark:text-red-400';
      case 'medium':
        return 'text-yellow-600 dark:text-yellow-400';
      case 'low':
        return 'text-gray-600 dark:text-gray-400';
      default:
        return 'text-gray-600 dark:text-gray-400';
    }
  };

  const renderIntentCard = (card: IntentCard) => {
    return (
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {card.title}
            </h3>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                card.status
              )}`}
            >
              {card.status}
            </span>
            <span className={`text-xs font-medium ${getPriorityColor(card.priority)}`}>
              {card.priority}
            </span>
          </div>
          {card.description && (
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
              {card.description}
            </p>
          )}
          {card.progress_percentage !== undefined && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                <span>Progress</span>
                <span>{card.progress_percentage}%</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all"
                  style={{ width: `${card.progress_percentage}%` }}
                />
              </div>
            </div>
          )}
          {card.metadata?.source && (
            <div className="flex items-center gap-2 mt-2">
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Source: {card.metadata.source}
              </p>
              {card.metadata.source === 'intent_steward_auto' && (
                <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
                  Auto-updated by Intent Steward
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {t('intentPanel.title' as any) || 'Intent Panel'}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('intentPanel.subtitle' as any) || 'Manage your long-term intents and projects'}
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Filters and Search */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 space-y-3">
          <div className="flex gap-2 flex-wrap">
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${filter === 'all'
                    ? 'bg-blue-600 text-white dark:bg-blue-700'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
              >
                {t('intentPanel.all' as any) || 'All'}
              </button>
              <button
                onClick={() => setFilter('active')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${filter === 'active'
                    ? 'bg-blue-600 text-white dark:bg-blue-700'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
              >
                {t('intentPanel.active' as any) || 'Active'}
              </button>
              <button
                onClick={() => setFilter('completed')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${filter === 'completed'
                    ? 'bg-blue-600 text-white dark:bg-blue-700'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
              >
                {t('intentPanel.completed' as any) || 'Completed'}
              </button>
            </div>
            <div className="flex gap-2 ml-auto">
              <button
                onClick={() => setGroupBy(groupBy === 'cluster' ? 'none' : 'cluster')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${groupBy === 'cluster'
                    ? 'bg-green-600 text-white dark:bg-green-700'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
              >
                {groupBy === 'cluster' ? (t('intentPanel.groupedByCluster' as any) || 'Grouped by Cluster') : (t('intentPanel.groupByCluster' as any) || 'Group by Cluster')}
              </button>
            </div>
          </div>
          {/* Search bar */}
          <div className="relative">
            <input
              type="text"
              placeholder={t('intentPanel.searchPlaceholder' as any) || 'Search intents...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 pl-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <svg
              className="absolute left-3 top-2.5 h-5 w-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-gray-500 dark:text-gray-400">
                {t('intentPanel.loading' as any) || 'Loading...'}
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-4">
              <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
            </div>
          )}

          {!loading && !error && intentCards.length === 0 && (
            <div className="text-center py-12">
              <svg
                className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
              <p className="mt-4 text-gray-500 dark:text-gray-400">
                {t('intentPanel.noIntents' as any) || 'No intent cards found'}
              </p>
              <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
                {t('intentPanel.noIntentsHint' as any) || 'Intent cards will appear here when created'}
              </p>
            </div>
          )}

          {!loading && !error && intentCards.length > 0 && (
            <div className="space-y-6">
              {groupBy === 'cluster' ? (
                // Group by cluster
                (() => {
                  // Filter by search query first
                  const filteredCards = searchQuery
                    ? intentCards.filter(card =>
                      card.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                      card.description?.toLowerCase().includes(searchQuery.toLowerCase())
                    )
                    : intentCards;

                  const clusters: Record<string, IntentCard[]> = {};
                  const unclustered: IntentCard[] = [];

                  filteredCards.forEach(card => {
                    const clusterLabel = card.metadata?.cluster_label;
                    if (clusterLabel) {
                      if (!clusters[clusterLabel]) {
                        clusters[clusterLabel] = [];
                      }
                      clusters[clusterLabel].push(card);
                    } else {
                      unclustered.push(card);
                    }
                  });

                  return (
                    <>
                      {Object.entries(clusters).map(([clusterLabel, cards]) => {
                        const isExpanded = expandedClusters.has(clusterLabel);
                        return (
                          <div key={clusterLabel} className="space-y-3">
                            <div
                              className="flex items-center gap-2 mb-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 p-2 rounded"
                              onClick={() => {
                                const newExpanded = new Set(expandedClusters);
                                if (isExpanded) {
                                  newExpanded.delete(clusterLabel);
                                } else {
                                  newExpanded.add(clusterLabel);
                                }
                                setExpandedClusters(newExpanded);
                              }}
                            >
                              <svg
                                className={`w-4 h-4 text-gray-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                              <h4 className="text-md font-semibold text-gray-700 dark:text-gray-300">
                                {clusterLabel}
                              </h4>
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                ({cards.length} {cards.length === 1 ? 'intent' : 'intents'})
                              </span>
                            </div>
                            {isExpanded && (
                              <div className="space-y-3 pl-4 border-l-2 border-blue-200 dark:border-blue-700">
                                {cards.map((card) => (
                                  <div
                                    key={card.id}
                                    className="bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                                  >
                                    {renderIntentCard(card)}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {unclustered.length > 0 && (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 mb-2">
                            <h4 className="text-md font-semibold text-gray-700 dark:text-gray-300">
                              {t('intentPanel.unclustered' as any) || 'Unclustered'}
                            </h4>
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              ({unclustered.length} {unclustered.length === 1 ? 'intent' : 'intents'})
                            </span>
                          </div>
                          <div className="space-y-3 pl-4 border-l-2 border-gray-200 dark:border-gray-700">
                            {unclustered.map((card) => (
                              <div
                                key={card.id}
                                className="bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                              >
                                {renderIntentCard(card)}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  );
                })()
              ) : (
                // No grouping - show all cards (filtered by search)
                (() => {
                  const filteredCards = searchQuery
                    ? intentCards.filter(card =>
                      card.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                      card.description?.toLowerCase().includes(searchQuery.toLowerCase())
                    )
                    : intentCards;

                  return filteredCards.map((card) => (
                    <div
                      key={card.id}
                      className="bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                    >
                      {renderIntentCard(card)}
                    </div>
                  ));
                })()
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
          <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
            <span>
              {t('intentPanel.total' as any) || 'Total'}: {intentCards.length} {t('intentPanel.intents' as any) || 'intents'}
            </span>
            <span>
              {t('intentPanel.phase0Note' as any) || 'Phase 0: Metrics collection active'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

