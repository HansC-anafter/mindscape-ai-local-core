'use client';

/**
 * DesignSnapshotCard - Specialized card component for Design Snapshot artifacts
 *
 * Displays design snapshot metadata, variants, quality info, and actions.
 * Used in ArtifactsPane when artifact.kind === 'design_snapshot'
 */

import React, { useState } from 'react';
import { useBaselineStatus } from '@/hooks/useBaselineStatus';
import { DesignSnapshotPreview } from './DesignSnapshotPreview';

// ============================================================================
// Types
// ============================================================================

interface DesignSnapshotMetadata {
  kind: string;
  source_tool?: string;
  version?: string;
  snapshot_date?: string;
  variant_id?: string;
  active_variant?: string;
  baseline_for?: string;
  lock_mode?: 'locked' | 'advisory';
  extraction_quality?: 'low' | 'medium' | 'high';
  missing_fields?: string[];
  related_snapshots?: string[];
}

interface Artifact {
  id: string;
  title: string;
  summary?: string;
  artifact_type?: string;
  metadata?: any;
  created_at: string;
  updated_at?: string;
}

interface DesignSnapshotCardProps {
  artifact: Artifact;
  workspaceId: string;
  projectId?: string;
  onSetBaseline?: (snapshotId: string, variantId?: string) => void;
  onPreview?: (snapshotId: string) => void;
  onDiff?: (snapshotId: string) => void;
  onExport?: (snapshotId: string) => void;
  isHighlighted?: boolean;
  // Preview content (if available)
  htmlContent?: string;
  cssContent?: string;
  screenshotUrl?: string;
}

// ============================================================================
// Component
// ============================================================================

export function DesignSnapshotCard({
  artifact,
  workspaceId,
  projectId,
  onSetBaseline,
  onPreview,
  onDiff,
  onExport,
  isHighlighted = false,
  htmlContent,
  cssContent,
  screenshotUrl,
}: DesignSnapshotCardProps) {
  const metadata = (artifact.metadata || {}) as DesignSnapshotMetadata;
  const { context } = useBaselineStatus(workspaceId, projectId);
  const [showPreview, setShowPreview] = useState(false);

  // Check if this snapshot is applied as baseline
  const isApplied =
    context?.snapshotId === artifact.id ||
    metadata.baseline_for === projectId;

  // Check if locked
  const isLocked = metadata.lock_mode === 'locked' || context?.lockMode === 'locked';

  // Format date
  const formatDate = (dateStr?: string): string => {
    if (!dateStr) return 'Unknown';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Unknown';
    }
  };

  // Handle set baseline
  const handleSetBaseline = (e: React.MouseEvent, variantId?: string) => {
    e.stopPropagation();
    onSetBaseline?.(artifact.id, variantId);
  };

  // Handle lock/unlock
  const handleLock = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isLocked) {
      // Unlock: set baseline with advisory lock_mode
      onSetBaseline?.(artifact.id, metadata.variant_id);
    } else {
      // Lock: set baseline with locked lock_mode
      onSetBaseline?.(artifact.id, metadata.variant_id);
    }
  };

  // Handle preview
  const handlePreview = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (htmlContent || screenshotUrl) {
      setShowPreview(!showPreview);
    }
    onPreview?.(artifact.id);
  };

  // Handle diff
  const handleDiff = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDiff?.(artifact.id);
  };

  // Handle export
  const handleExport = (e: React.MouseEvent) => {
    e.stopPropagation();
    onExport?.(artifact.id);
  };

  return (
    <div
      className={`
        border rounded-lg p-4 bg-white dark:bg-gray-900 hover:shadow-md transition-shadow
        ${isHighlighted
          ? 'border-blue-400 dark:border-blue-500 shadow-lg bg-blue-50 dark:bg-blue-900/20'
          : 'border-gray-200 dark:border-gray-700'
        }
      `}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xl">🎨</span>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Design Snapshot {metadata.version || 'v?.?.?'}
            </h3>
            {isApplied && (
              <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded font-medium">
                Applied
              </span>
            )}
            {isLocked && (
              <span className="text-purple-500" title="Locked">
                🔒
              </span>
            )}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            Source: {metadata.source_tool || 'Unknown'} • Created:{' '}
            {formatDate(metadata.snapshot_date)}
          </div>
        </div>
      </div>

      {/* Variants Picker */}
      {metadata.variant_id && (
        <div className="mb-3">
          <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">
            Variant:
          </label>
          <div className="flex gap-2">
            <button
              onClick={(e) => handleSetBaseline(e, metadata.variant_id)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                metadata.variant_id === metadata.active_variant ||
                metadata.variant_id === context?.variantId
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 ring-2 ring-blue-500'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {metadata.variant_id}
            </button>
            {/* If there are related snapshots, show them as other variants */}
            {metadata.related_snapshots &&
              metadata.related_snapshots.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-gray-500">
                  <span>+{metadata.related_snapshots.length} more</span>
                </div>
              )}
          </div>
        </div>
      )}

      {/* Quality & Missing Fields */}
      <div className="mb-3 space-y-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-600 dark:text-gray-400">Quality:</span>
          <QualityBadge quality={metadata.extraction_quality || 'medium'} />
          {metadata.missing_fields && metadata.missing_fields.length > 0 && (
            <>
              <span className="text-gray-400">•</span>
              <span className="text-gray-600 dark:text-gray-400">
                Missing: {metadata.missing_fields.slice(0, 3).join(', ')}
                {metadata.missing_fields.length > 3 &&
                  ` +${metadata.missing_fields.length - 3} more`}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-3 border-t border-gray-200 dark:border-gray-700 flex-wrap">
        {!isApplied && (
          <button
            onClick={(e) => handleSetBaseline(e)}
            className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors"
          >
            Set as Baseline
          </button>
        )}

        {isApplied && (
          <>
            <button
              onClick={handleLock}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-1"
            >
              <span>{isLocked ? '🔓' : '🔒'}</span>
              <span>{isLocked ? 'Unlock' : 'Lock'}</span>
            </button>

            <button
              onClick={handlePreview}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-1"
            >
              <span>👁️</span>
              <span>Preview</span>
            </button>

            <button
              onClick={handleDiff}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-1"
            >
              <span>🔀</span>
              <span>Diff</span>
            </button>

            <button
              onClick={handleExport}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-1"
            >
              <span>📤</span>
              <span>Export</span>
            </button>
          </>
        )}
      </div>

      {/* Preview Section */}
      {showPreview && (htmlContent || screenshotUrl) && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <DesignSnapshotPreview
            htmlContent={htmlContent || ''}
            cssContent={cssContent || ''}
            screenshotUrl={screenshotUrl}
            snapshotId={artifact.id}
            mode="safe"
            className="w-full"
          />
        </div>
      )}
    </div>
  );
}

// ============================================================================
// QualityBadge Component
// ============================================================================

function QualityBadge({
  quality,
}: {
  quality: 'low' | 'medium' | 'high';
}) {
  const config: Record<
    'low' | 'medium' | 'high',
    { label: string; className: string; icon: string }
  > = {
    low: {
      label: 'Low',
      className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
      icon: '⚠️',
    },
    medium: {
      label: 'Medium',
      className:
        'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
      icon: '⚡',
    },
    high: {
      label: 'High',
      className:
        'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
      icon: '✓',
    },
  };

  const { label, className, icon } = config[quality];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${className}`}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </span>
  );
}
