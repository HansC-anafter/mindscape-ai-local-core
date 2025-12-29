'use client';

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { GraphView } from './GraphView';
import { MatrixView } from './MatrixView';
import type { EffectiveLens, LensNodeState } from '@/lib/lens-api';

// Use GraphView instead of GraphViewEnhanced to avoid WebGL SSR issues
// GraphViewEnhanced requires WebGL which causes SSR errors
const GraphViewEnhanced = dynamic(() => import('./GraphViewEnhanced').then(mod => ({ default: mod.GraphViewEnhanced })), {
  ssr: false,
  loading: () => <div className="h-full flex items-center justify-center text-gray-500">Loading graph...</div>
});

type ViewMode = 'graph' | 'matrix';
type ScopeFilter = 'all' | 'global' | 'workspace' | 'session';

interface PalettePanelProps {
  effectiveLens: EffectiveLens | null;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  onNodeStateChange?: (nodeId: string, state: LensNodeState) => void;
  selectedNodes: string[];
  onNodeSelect: (nodeId: string) => void;
  onNodeHover?: (nodeId: string | null) => void;
}

export function PalettePanel({
  effectiveLens,
  viewMode,
  onViewModeChange,
  onNodeStateChange,
  selectedNodes,
  onNodeSelect,
  onNodeHover,
}: PalettePanelProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [useEnhancedGraph, setUseEnhancedGraph] = useState(true);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');

  const handleNodeHover = (nodeId: string | null) => {
    setHoveredNode(nodeId);
    onNodeHover?.(nodeId);
  };

  // Filter nodes by scope
  const filteredNodes = effectiveLens
    ? effectiveLens.nodes.filter((node) => {
        if (scopeFilter === 'all') return true;
        return node.effective_scope === scopeFilter;
      })
    : [];

  if (!effectiveLens) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full flex items-center justify-center">
        <p className="text-gray-500">No effective lens available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full flex flex-col">
      {/* Header with View Mode Toggle and Scope Filter */}
      <div className="p-4 border-b border-gray-200 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Graph / Matrix</h2>
          <div className="flex space-x-2">
            <button
              onClick={() => onViewModeChange('graph')}
              className={`px-3 py-1 rounded text-sm font-medium ${
                viewMode === 'graph'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Graph
            </button>
            <button
              onClick={() => onViewModeChange('matrix')}
              className={`px-3 py-1 rounded text-sm font-medium ${
                viewMode === 'matrix'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Matrix
            </button>
          </div>
        </div>
        {/* Scope Filter */}
        <div className="flex items-center space-x-2">
          <span className="text-xs text-gray-600 font-medium">套用範圍：</span>
          <div className="flex space-x-1">
            <button
              onClick={() => setScopeFilter('all')}
              className={`px-2 py-1 rounded text-xs font-medium ${
                scopeFilter === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setScopeFilter('global')}
              className={`px-2 py-1 rounded text-xs font-medium ${
                scopeFilter === 'global'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Global
            </button>
            <button
              onClick={() => setScopeFilter('workspace')}
              className={`px-2 py-1 rounded text-xs font-medium ${
                scopeFilter === 'workspace'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Workspace
            </button>
            <button
              onClick={() => setScopeFilter('session')}
              className={`px-2 py-1 rounded text-xs font-medium ${
                scopeFilter === 'session'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Session
            </button>
          </div>
          <span className="text-xs text-gray-500 ml-2">
            ({filteredNodes.length} / {effectiveLens.nodes.length})
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'graph' ? (
          useEnhancedGraph ? (
            <GraphViewEnhanced
              nodes={filteredNodes}
              selectedNodes={selectedNodes}
              onNodeSelect={onNodeSelect}
              onNodeHover={handleNodeHover}
            />
          ) : (
            <GraphView
              nodes={filteredNodes}
              selectedNodes={selectedNodes}
              onNodeSelect={onNodeSelect}
              onNodeHover={handleNodeHover}
            />
          )
        ) : (
          <MatrixView
            nodes={filteredNodes}
            onStateChange={onNodeStateChange}
            selectedNodes={selectedNodes}
            onNodeSelect={onNodeSelect}
            onNodeHover={handleNodeHover}
          />
        )}
      </div>

      {/* Footer Info */}
      <div className="p-2 border-t border-gray-200 bg-gray-50 flex items-center justify-between text-xs text-gray-600">
        <span>
          {viewMode === 'graph' ? (
            '只讀模式：可選取、hover，不可改狀態'
          ) : (
            '編輯模式：可調整節點狀態（OFF/KEEP/EMPHASIZE）'
          )}
        </span>
        {viewMode === 'graph' && (
          <button
            onClick={() => setUseEnhancedGraph(!useEnhancedGraph)}
            className="px-2 py-1 bg-gray-200 hover:bg-gray-300 rounded text-xs"
          >
            {useEnhancedGraph ? '切換到列表視圖' : '切換到圖形視圖'}
          </button>
        )}
      </div>
    </div>
  );
}

