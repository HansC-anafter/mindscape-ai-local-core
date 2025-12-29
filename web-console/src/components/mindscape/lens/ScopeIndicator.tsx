'use client';

import React from 'react';
import type { EffectiveLens } from '@/lib/lens-api';

interface ScopeIndicatorProps {
  effectiveLens: EffectiveLens | null;
}

export function ScopeIndicator({ effectiveLens }: ScopeIndicatorProps) {
  if (!effectiveLens) {
    return (
      <div className="text-xs text-gray-500">無有效 Lens</div>
    );
  }

  const hasWorkspaceOverride = effectiveLens.workspace_override_count > 0;
  const hasSessionOverride = effectiveLens.session_override_count > 0;

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-gray-700">套用範圍</div>

      <div className="space-y-1">
        {/* Global Scope */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center">
            <span className="text-xs text-gray-600">🌐</span>
            <span className="text-xs text-gray-700 ml-1">全域</span>
          </div>
          {!hasWorkspaceOverride && !hasSessionOverride && (
            <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">預設</span>
          )}
        </div>

        {/* Workspace Override */}
        {hasWorkspaceOverride && (
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="text-xs text-gray-600">📁</span>
              <span className="text-xs text-gray-700 ml-1">Workspace 覆寫</span>
            </div>
            <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-700 rounded">
              {effectiveLens.workspace_override_count} 個節點
            </span>
          </div>
        )}

        {/* Session Override */}
        {hasSessionOverride && (
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <span className="text-xs text-gray-600">🧪</span>
              <span className="text-xs text-gray-700 ml-1">Session 實驗</span>
            </div>
            <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">
              {effectiveLens.session_override_count} 個節點
            </span>
          </div>
        )}
      </div>

      {/* Summary */}
      {hasWorkspaceOverride || hasSessionOverride ? (
        <div className="text-xs text-gray-500 italic">
          當前使用三層疊加配置
        </div>
      ) : (
        <div className="text-xs text-gray-500 italic">
          使用全域預設配置
        </div>
      )}
    </div>
  );
}

