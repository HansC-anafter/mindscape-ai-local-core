'use client';

import React from 'react';
import useSWR from 'swr';
import { getApiBaseUrl } from '@/lib/api-url';
import type { MindLensProfile, PresetDiff } from '@/lib/lens-api';

interface PresetCardProps {
  profile: MindLensProfile;
  activePresetId?: string;
  onSelect: (id: string) => void;
  onViewDiff?: (id: string) => void;
}

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`Failed to fetch: ${res.status}`);
  }
  return res.json();
};

export function PresetCard({
  profile,
  activePresetId,
  onSelect,
  onViewDiff,
}: PresetCardProps) {
  const { data: diff } = useSWR<PresetDiff>(
    activePresetId && activePresetId !== profile.id
      ? `${getApiBaseUrl()}/api/v1/mindscape/lens/profiles/${activePresetId}/diff?compare_with=${profile.id}`
      : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  const isActive = activePresetId === profile.id;
  const hasDiff = diff && diff.changes.length > 0;

  return (
    <div
      className={`p-3 rounded-lg border cursor-pointer transition-all ${isActive
          ? 'bg-blue-50 border-blue-200 shadow-sm'
          : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm'
        }`}
      onClick={() => onSelect(profile.id)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2">
            <h3 className={`text-sm font-medium ${isActive ? 'text-blue-900' : 'text-gray-900'}`}>
              {profile.name}
            </h3>
            {profile.is_default && (
              <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                Default
              </span>
            )}
            {isActive && (
              <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
                Active
              </span>
            )}
          </div>

          {hasDiff && !isActive && (
            <div className="mt-2 space-y-1">
              <div className="text-xs text-gray-600">
                {(diff.strengthened_count ?? 0) > 0 && (
                  <span className="text-green-600">+{diff.strengthened_count} strengthened</span>
                )}
                {(diff.weakened_count ?? 0) > 0 && (
                  <span className="ml-2 text-yellow-600">-{diff.weakened_count} weakened</span>
                )}
                {(diff.disabled_count ?? 0) > 0 && (
                  <span className="ml-2 text-gray-600">{diff.disabled_count} disabled</span>
                )}
                {(diff.enabled_count ?? 0) > 0 && (
                  <span className="ml-2 text-blue-600">+{diff.enabled_count} enabled</span>
                )}
              </div>
              {onViewDiff && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewDiff(profile.id);
                  }}
                  className="text-xs text-blue-600 hover:text-blue-800"
                >
                  View detailed diff
                </button>
              )}
            </div>
          )}

          {diff && diff.changes.length === 0 && !isActive && (
            <div className="mt-2 text-xs text-gray-500">No differences from current preset</div>
          )}
        </div>

        <div className="flex items-center space-x-1 ml-2">
          {!isActive && onViewDiff && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onViewDiff(profile.id);
              }}
              className="p-1 text-gray-400 hover:text-blue-600"
              title="View diff"
            >
              DIFF
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
