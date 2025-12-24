'use client';

/**
 * BaselineDiffPanel - Component for displaying baseline diff visualization
 *
 * Shows differences between baseline snapshot and current spec/outline:
 * - Sections (added/removed/modified)
 * - Theme tokens (colors, typography, spacing)
 * - Missing fields
 */

import React, { useState, useEffect } from 'react';
import { useAPIClient } from '@/hooks/useAPIClient';

// ============================================================================
// Types
// ============================================================================

interface BaselineDiffPanelProps {
  workspaceId: string;
  snapshotId: string;
  projectId?: string;
  onClose?: () => void;
}

interface DiffSummary {
  sections: Array<{
    type: 'added' | 'removed' | 'modified';
    name: string;
    location: string;
  }>;
  theme_tokens: {
    colors: Record<string, { baseline: any; current: any }>;
    typography: Record<string, { baseline: any; current: any }>;
    spacing?: { baseline: any[]; current: any[] };
  };
  missing_fields: string[];
}

interface DiffResponse {
  diff_summary: DiffSummary;
  baseline_version: string;
  current_spec_version?: string;
  current_outline_version?: string;
}

// ============================================================================
// Component
// ============================================================================

export function BaselineDiffPanel({
  workspaceId,
  snapshotId,
  projectId,
  onClose,
}: BaselineDiffPanelProps) {
  const apiClient = useAPIClient();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diffData, setDiffData] = useState<DiffResponse | null>(null);

  useEffect(() => {
    const fetchDiff = async () => {
      try {
        setLoading(true);
        setError(null);

        const queryParams = new URLSearchParams({
          snapshot_id: snapshotId,
          compare_with_spec: 'true',
        });
        if (projectId) {
          queryParams.append('project_id', projectId);
        }

        const response = await apiClient.get(
          `/api/v1/workspaces/${workspaceId}/web-generation/baseline/diff?${queryParams.toString()}`
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `Failed to fetch diff: ${response.statusText}`);
        }

        const data: DiffResponse = await response.json();
        setDiffData(data);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    fetchDiff();
  }, [workspaceId, snapshotId, projectId, apiClient]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-sm text-secondary">
          <div className="w-4 h-4 border-2 border-default border-t-gray-600 rounded-full animate-spin" />
          Loading diff...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
        <div className="text-sm text-red-600 dark:text-red-400">
          ⚠️ Error: {error}
        </div>
      </div>
    );
  }

  if (!diffData) {
    return null;
  }

  const { diff_summary, baseline_version, current_spec_version } = diffData;

  return (
    <div className="bg-surface-accent dark:bg-gray-900 border border-default dark:border-gray-700 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-default dark:border-gray-700">
        <div>
          <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
            Baseline Diff
          </h2>
          <p className="text-xs text-secondary dark:text-gray-400 mt-1">
            v{baseline_version} → {current_spec_version || 'current'}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-tertiary hover:text-secondary dark:hover:text-gray-300"
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Sections Diff */}
        {diff_summary.sections.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
              Sections
            </h3>
            <div className="space-y-1">
              {diff_summary.sections.map((section, index) => (
                <div
                  key={index}
                  className={`flex items-center gap-2 text-sm px-3 py-2 rounded ${
                    section.type === 'added'
                      ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                      : section.type === 'removed'
                      ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                      : 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300'
                  }`}
                >
                  <span>
                    {section.type === 'added' && '➕'}
                    {section.type === 'removed' && '➖'}
                    {section.type === 'modified' && '✏️'}
                  </span>
                  <span className="font-medium">{section.name}</span>
                  <span className="text-xs opacity-70">({section.type})</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Theme Tokens Diff */}
        {(Object.keys(diff_summary.theme_tokens.colors).length > 0 ||
          Object.keys(diff_summary.theme_tokens.typography).length > 0 ||
          diff_summary.theme_tokens.spacing) && (
          <div>
            <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
              Theme Tokens
            </h3>

            {/* Colors */}
            {Object.keys(diff_summary.theme_tokens.colors).length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-medium text-primary dark:text-gray-300 mb-2">
                  Colors
                </h4>
                <div className="space-y-2">
                  {Object.entries(diff_summary.theme_tokens.colors).map(([key, diff]) => (
                    <div
                      key={key}
                      className="flex items-center gap-3 text-sm px-3 py-2 bg-surface-secondary dark:bg-gray-800 rounded"
                    >
                      <span className="font-medium text-primary dark:text-gray-300 min-w-[100px]">
                        {key}:
                      </span>
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-secondary dark:text-gray-400 font-mono text-xs">
                          {String(diff.baseline || '—')}
                        </span>
                        <span className="text-tertiary">→</span>
                        <span className="text-blue-600 dark:text-blue-400 font-mono text-xs">
                          {String(diff.current || '—')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Typography */}
            {Object.keys(diff_summary.theme_tokens.typography).length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-medium text-primary dark:text-gray-300 mb-2">
                  Typography
                </h4>
                <div className="space-y-2">
                  {Object.entries(diff_summary.theme_tokens.typography).map(([key, diff]) => (
                    <div
                      key={key}
                      className="flex items-center gap-3 text-sm px-3 py-2 bg-surface-secondary dark:bg-gray-800 rounded"
                    >
                      <span className="font-medium text-primary dark:text-gray-300 min-w-[100px]">
                        {key}:
                      </span>
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-secondary dark:text-gray-400 font-mono text-xs">
                          {String(diff.baseline || '—')}
                        </span>
                        <span className="text-tertiary">→</span>
                        <span className="text-blue-600 dark:text-blue-400 font-mono text-xs">
                          {String(diff.current || '—')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Spacing */}
            {diff_summary.theme_tokens.spacing && (
              <div>
                <h4 className="text-xs font-medium text-primary dark:text-gray-300 mb-2">
                  Spacing
                </h4>
                <div className="flex items-center gap-3 text-sm px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Scale:</span>
                  <div className="flex items-center gap-2 flex-1">
                    <span className="text-gray-600 dark:text-gray-400 font-mono text-xs">
                      [{Array.isArray(diff_summary.theme_tokens.spacing.baseline) ? diff_summary.theme_tokens.spacing.baseline.join(', ') : '—'}]
                    </span>
                    <span className="text-gray-400">→</span>
                    <span className="text-blue-600 dark:text-blue-400 font-mono text-xs">
                      [{Array.isArray(diff_summary.theme_tokens.spacing.current) ? diff_summary.theme_tokens.spacing.current.join(', ') : '—'}]
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Missing Fields */}
        {diff_summary.missing_fields.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
              Missing Fields
            </h3>
            <div className="space-y-1">
              {diff_summary.missing_fields.map((field, index) => (
                <div
                  key={index}
                  className="flex items-center gap-2 text-sm px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300 rounded"
                >
                  <span>⚠️</span>
                  <span>{field}</span>
                  <span className="text-xs opacity-70">(baseline only)</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {diff_summary.sections.length === 0 &&
          Object.keys(diff_summary.theme_tokens.colors).length === 0 &&
          Object.keys(diff_summary.theme_tokens.typography).length === 0 &&
          !diff_summary.theme_tokens.spacing &&
          diff_summary.missing_fields.length === 0 && (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <div className="text-4xl mb-2">✓</div>
              <div className="text-sm">No differences found</div>
            </div>
          )}
      </div>
    </div>
  );
}
