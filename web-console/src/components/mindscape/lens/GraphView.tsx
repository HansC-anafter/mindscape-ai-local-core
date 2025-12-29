'use client';

import React from 'react';
import type { LensNode } from '@/lib/lens-api';

interface GraphViewProps {
  nodes: LensNode[];
  selectedNodes: string[];
  onNodeSelect: (nodeId: string) => void;
  onNodeHover: (nodeId: string | null) => void;
}

export function GraphView({
  nodes,
  selectedNodes,
  onNodeSelect,
  onNodeHover,
}: GraphViewProps) {
  if (!nodes || nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No nodes available</p>
      </div>
    );
  }

  const groupedNodes = nodes.reduce((acc, node) => {
    const category = node.category || 'other';
    if (!acc[category]) acc[category] = [];
    acc[category].push(node);
    return acc;
  }, {} as Record<string, LensNode[]>);

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="space-y-4">
        {Object.entries(groupedNodes).map(([category, categoryNodes]) => (
          <div key={category} className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-700 uppercase">{category}</h3>
            <div className="grid grid-cols-2 gap-2">
              {categoryNodes.map((node) => (
                <div
                  key={node.node_id}
                  onClick={() => onNodeSelect(node.node_id)}
                  onMouseEnter={() => onNodeHover(node.node_id)}
                  onMouseLeave={() => onNodeHover(null)}
                  className={`
                    p-3 rounded-lg border-2 cursor-pointer transition-all
                    ${
                      selectedNodes.includes(node.node_id)
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }
                    ${node.state === 'off' ? 'opacity-50' : ''}
                    ${node.state === 'emphasize' ? 'ring-2 ring-yellow-400' : ''}
                  `}
                >
                  <div className="text-sm font-medium text-gray-900">{node.node_label}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    {node.node_type} • {node.state}
                  </div>
                  {node.is_overridden && (
                    <div className="text-xs text-blue-600 mt-1">
                      Overridden from {node.overridden_from}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

