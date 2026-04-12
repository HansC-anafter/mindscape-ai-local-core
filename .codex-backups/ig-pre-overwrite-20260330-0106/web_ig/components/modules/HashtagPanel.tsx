'use client';

/**
 * Hashtag Panel
 *
 * Features:
 * - Hashtag group management (brand fixed, theme, campaign)
 * - Hashtag combination functionality
 * - Blocked hashtag checking
 */

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { Hash, Plus, Search, CheckCircle2, XCircle } from 'lucide-react';

interface HashtagPanelProps {
  workspaceId: string;
  apiUrl: string;
}

interface HashtagGroup {
  name: string;
  type: 'brand' | 'theme' | 'campaign';
  hashtags: string[];
}

export default function HashtagPanel({
  workspaceId,
  apiUrl
}: HashtagPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [hashtagGroups, setHashtagGroups] = useState<HashtagGroup[]>([]);
  const [recommendedHashtags, setRecommendedHashtags] = useState<string[]>([]);
  const [blockedHashtags, setBlockedHashtags] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<'education' | 'traffic' | 'conversion' | 'brand'>('education');
  const [audience, setAudience] = useState('');
  const [region, setRegion] = useState('');
  const [hashtagCount, setHashtagCount] = useState(30);

  useEffect(() => {
    loadHashtagGroups();
  }, [workspaceId, apiUrl]);

  const loadHashtagGroups = async () => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_hashtag_manager',
        inputs: {
          action: 'load_groups'
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        const groups = data.result?.hashtag_groups || [];
        setHashtagGroups(groups);
      }
    } catch (err) {
      console.error('Failed to load hashtag groups:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCombineHashtags = async () => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_hashtag_manager',
        inputs: {
          action: 'recommend',
          intent,
          audience: audience || undefined,
          region: region || undefined,
          hashtag_count: hashtagCount
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        setRecommendedHashtags(data.result?.recommended_hashtags || []);
        setBlockedHashtags(data.result?.blocked_hashtags || []);
      }
    } catch (err) {
      console.error('Failed to combine hashtags:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCheckBlocked = async (hashtags: string[]) => {
    if (hashtags.length === 0) return;

    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_hashtag_manager',
        inputs: {
          action: 'check_blocked',
          hashtags
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        setBlockedHashtags(data.result?.blocked_hashtags || []);
      }
    } catch (err) {
      console.error('Failed to check blocked hashtags:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          Hashtag Management
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4">
        {/* Combine Hashtags */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Combine Hashtags
          </h3>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-700 dark:text-gray-300 mb-1 block">
                Intent
              </label>
              <select
                value={intent}
                onChange={(e) => setIntent(e.target.value as typeof intent)}
                className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              >
                <option value="education">Education</option>
                <option value="traffic">Traffic</option>
                <option value="conversion">Conversion</option>
                <option value="brand">Brand</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-700 dark:text-gray-300 mb-1 block">
                Audience
              </label>
              <input
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="Optional"
                className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              />
            </div>

            <div>
              <label className="text-xs text-gray-700 dark:text-gray-300 mb-1 block">
                Region
              </label>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="Optional"
                className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              />
            </div>

            <div>
              <label className="text-xs text-gray-700 dark:text-gray-300 mb-1 block">
                Count
              </label>
              <input
                type="number"
                value={hashtagCount}
                onChange={(e) => setHashtagCount(parseInt(e.target.value, 10) || 30)}
                min={1}
                max={100}
                className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              />
            </div>

            <button
              onClick={handleCombineHashtags}
              disabled={loading}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Hash className="w-4 h-4" />
              Generate Hashtags
            </button>
          </div>
        </div>

        {/* Recommended Hashtags */}
        {recommendedHashtags.length > 0 && (
          <div className="bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800 p-4">
            <h3 className="text-sm font-semibold text-green-900 dark:text-green-100 mb-2">
              Recommended Hashtags ({recommendedHashtags.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {recommendedHashtags.map((tag, index) => (
                <span
                  key={index}
                  className="px-2 py-1 text-xs bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300 rounded"
                >
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Blocked Hashtags */}
        {blockedHashtags.length > 0 && (
          <div className="bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 p-4">
            <h3 className="text-sm font-semibold text-red-900 dark:text-red-100 mb-2">
              Blocked Hashtags ({blockedHashtags.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {blockedHashtags.map((tag, index) => (
                <span
                  key={index}
                  className="px-2 py-1 text-xs bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 rounded flex items-center gap-1"
                >
                  <XCircle className="w-3 h-3" />
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Hashtag Groups */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Hashtag Groups
          </h3>
          <div className="space-y-3">
            {loading ? (
              <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
                Loading...
              </div>
            ) : hashtagGroups.length === 0 ? (
              <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
                No groups
              </div>
            ) : (
              hashtagGroups.map((group, index) => (
                <div
                  key={index}
                  className="p-3 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {group.name}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {group.type}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {group.hashtags.slice(0, 10).map((tag, tagIndex) => (
                      <span
                        key={tagIndex}
                        className="px-1.5 py-0.5 text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded"
                      >
                        #{tag}
                      </span>
                    ))}
                    {group.hashtags.length > 10 && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        +{group.hashtags.length - 10} more
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
