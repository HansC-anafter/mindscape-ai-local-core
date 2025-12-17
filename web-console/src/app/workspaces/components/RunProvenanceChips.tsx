'use client';

/**
 * RunProvenanceChips - Component for displaying execution provenance information
 *
 * Shows baseline constraints, input artifacts, and warnings for web-generation executions.
 * Displays chips that link to related artifacts.
 */

import React from 'react';
import { useRouter } from 'next/navigation';

// ============================================================================
// Types
// ============================================================================

export interface ExecutionProvenance {
  constrainedBy?: {
    snapshotId: string;
    snapshotVersion: string;
    variantId?: string;
    lockMode: 'locked' | 'advisory';
  };
  inferred?: boolean; // If no baseline was applied, marked as inferred
  inputs?: {
    snapshot?: { id: string; version: string };
    outline?: { id: string; version: string };
    spec?: { id: string; version: string };
    themeConfig?: { id: string; version: string };
  };
  warnings?: Array<{
    type: 'stale' | 'missing' | 'partial-extraction';
    message: string;
  }>;
}

interface RunProvenanceChipsProps {
  provenance?: ExecutionProvenance;
  workspaceId: string;
}

interface ProvenanceChipProps {
  type: 'snapshot' | 'outline' | 'spec' | 'themeConfig';
  label: string;
  onClick?: () => void;
  artifactId?: string;
}

// ============================================================================
// Component
// ============================================================================

export function RunProvenanceChips({
  provenance,
  workspaceId,
}: RunProvenanceChipsProps) {
  const router = useRouter();

  if (!provenance) {
    return null;
  }

  const handleChipClick = (artifactId?: string) => {
    if (artifactId) {
      router.push(`/workspaces/${workspaceId}/artifacts/${artifactId}`);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
      {/* Constraint Declaration */}
      <div className="mb-2 text-sm text-gray-600 dark:text-gray-400">
        {provenance.constrainedBy ? (
          <>
            <span className="font-medium">Constrained by</span> Design Snapshot{' '}
            <span className="font-mono font-semibold">
              v{provenance.constrainedBy.snapshotVersion}
            </span>
            {provenance.constrainedBy.variantId && (
              <>
                {' '}
                <span className="text-gray-500">(Variant: {provenance.constrainedBy.variantId})</span>
              </>
            )}
            {provenance.constrainedBy.lockMode === 'locked' && (
              <span className="ml-2 text-purple-600 dark:text-purple-400 font-medium">
                🔒 Locked
              </span>
            )}
          </>
        ) : (
          <>
            <span className="italic">No baseline applied;</span> inferred from outline.
            {provenance.inferred && (
              <span className="ml-2 text-xs text-yellow-600 dark:text-yellow-400">
                ⚠️ Inferred
              </span>
            )}
          </>
        )}
      </div>

      {/* Warnings */}
      {provenance.warnings && provenance.warnings.length > 0 && (
        <div className="mb-2 space-y-1">
          {provenance.warnings.map((warning, index) => (
            <div
              key={index}
              className={`text-xs px-2 py-1 rounded ${
                warning.type === 'stale'
                  ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300'
                  : warning.type === 'missing'
                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                  : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
              }`}
            >
              <span className="font-medium">
                {warning.type === 'stale' && '⚠️ Stale: '}
                {warning.type === 'missing' && '❌ Missing: '}
                {warning.type === 'partial-extraction' && '⚠️ Partial: '}
              </span>
              {warning.message}
            </div>
          ))}
        </div>
      )}

      {/* Provenance Chips */}
      {provenance.inputs && (
        <div className="flex flex-wrap gap-2">
          {provenance.inputs.snapshot && (
            <ProvenanceChip
              type="snapshot"
              label={`Snapshot v${provenance.inputs.snapshot.version}`}
              artifactId={provenance.inputs.snapshot.id}
              onClick={() => handleChipClick(provenance.inputs?.snapshot?.id)}
            />
          )}

          {provenance.inputs.outline && (
            <ProvenanceChip
              type="outline"
              label={`Outline v${provenance.inputs.outline.version}`}
              artifactId={provenance.inputs.outline.id}
              onClick={() => handleChipClick(provenance.inputs?.outline?.id)}
            />
          )}

          {provenance.inputs.spec && (
            <ProvenanceChip
              type="spec"
              label={`Spec v${provenance.inputs.spec.version}`}
              artifactId={provenance.inputs.spec.id}
              onClick={() => handleChipClick(provenance.inputs?.spec?.id)}
            />
          )}

          {provenance.inputs.themeConfig && (
            <ProvenanceChip
              type="themeConfig"
              label={`Theme v${provenance.inputs.themeConfig.version}`}
              artifactId={provenance.inputs.themeConfig.id}
              onClick={() => handleChipClick(provenance.inputs?.themeConfig?.id)}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// ProvenanceChip Component
// ============================================================================

function ProvenanceChip({
  type,
  label,
  onClick,
  artifactId,
}: ProvenanceChipProps) {
  const typeConfig: Record<
    string,
    { icon: string; className: string }
  > = {
    snapshot: {
      icon: '🎨',
      className:
        'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50',
    },
    outline: {
      icon: '📋',
      className:
        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50',
    },
    spec: {
      icon: '📄',
      className:
        'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-900/50',
    },
    themeConfig: {
      icon: '🎨',
      className:
        'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 hover:bg-orange-200 dark:hover:bg-orange-900/50',
    },
  };

  const config = typeConfig[type] || typeConfig.snapshot;

  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
        transition-colors cursor-pointer
        ${config.className}
        ${!onClick ? 'opacity-50 cursor-not-allowed' : ''}
      `}
      title={artifactId ? `View artifact: ${artifactId}` : undefined}
    >
      <span>{config.icon}</span>
      <span>{label}</span>
    </button>
  );
}
