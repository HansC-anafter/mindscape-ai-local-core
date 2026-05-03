'use client';

import React from 'react';
import type { EffectiveLens } from '@/lib/lens-api';

interface ScopeIndicatorProps {
  effectiveLens: EffectiveLens | null;
}

export function ScopeIndicator({ effectiveLens }: ScopeIndicatorProps) {
  if (!effectiveLens) {
    return (
      <div className="text-xs text-gray-500">No active Lens</div>
    );
  }

  const hasWorkspaceOverride = effectiveLens.workspace_override_count > 0;
  const hasSessionOverride = effectiveLens.session_override_count > 0;

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-gray-700">Applied Scope</div>

      <div className="space-y-1">
        <div className="flex items-center space-x-2">
          <div className="flex items-center">
            <span className="text-xs text-gray-600">GLOBAL</span>
            <span className="text-xs text-gray-700 ml-1">Global</span>
          </div>
          {!hasWorkspaceOverride && !hasSessionOverride && (
            <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">Default</span>
          )}
        </div>

        {hasWorkspaceOverride && (
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="text-xs text-gray-600">WORK</span>
              <span className="text-xs text-gray-700 ml-1">Workspace Override</span>
            </div>
            <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-700 rounded">
              {effectiveLens.workspace_override_count} nodes
            </span>
          </div>
        )}

        {hasSessionOverride && (
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="text-xs text-gray-600">SESSION</span>
              <span className="text-xs text-gray-700 ml-1">Session Experiment</span>
            </div>
            <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">
              {effectiveLens.session_override_count} nodes
            </span>
          </div>
        )}
      </div>

      {hasWorkspaceOverride || hasSessionOverride ? (
        <div className="text-xs text-gray-500 italic">
          Three-layer overlay is active
        </div>
      ) : (
        <div className="text-xs text-gray-500 italic">
          Global default is active
        </div>
      )}
    </div>
  );
}
