'use client';

import React from 'react';
import type { LensNode, LensNodeState } from '@/lib/lens-api';

interface MatrixViewProps {
  nodes: LensNode[];
  groupBy?: 'category' | 'type';
  onStateChange?: (nodeId: string, state: LensNodeState) => void;
  selectedNodes: string[];
  onNodeSelect: (nodeId: string) => void;
  onNodeHover?: (nodeId: string | null) => void;
}

export function MatrixView({
  nodes,
  groupBy = 'category',
  onStateChange,
  selectedNodes,
  onNodeSelect,
  onNodeHover,
}: MatrixViewProps) {
  if (!nodes || nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No nodes available</p>
      </div>
    );
  }

  const groupedNodes = nodes.reduce((acc, node) => {
    const key = groupBy === 'category' ? node.category : node.node_type;
    if (!acc[key]) acc[key] = [];
    acc[key].push(node);
    return acc;
  }, {} as Record<string, LensNode[]>);

  const handleStateChange = (nodeId: string, newState: LensNodeState) => {
    if (onStateChange) {
      onStateChange(nodeId, newState);
    }
  };

  // 进一步按 node_type 分组（如果 groupBy 是 category）
  const getNestedGroups = () => {
    if (groupBy === 'category') {
      const nested: Record<string, Record<string, LensNode[]>> = {};
      Object.entries(groupedNodes).forEach(([category, nodes]) => {
        nested[category] = nodes.reduce((acc, node) => {
          const type = node.node_type;
          if (!acc[type]) acc[type] = [];
          acc[type].push(node);
          return acc;
        }, {} as Record<string, LensNode[]>);
      });
      return nested;
    }
    return null;
  };

  const nestedGroups = getNestedGroups();

  const renderNodeItem = (node: LensNode) => (
    <div
      key={node.node_id}
      className={`
        flex items-center justify-between p-2 rounded border
        ${
          selectedNodes.includes(node.node_id)
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-200'
        }
      `}
    >
      <div
        className="flex-1 cursor-pointer"
        onClick={() => onNodeSelect(node.node_id)}
        onMouseEnter={() => onNodeHover?.(node.node_id)}
        onMouseLeave={() => onNodeHover?.(null)}
      >
        <div className="text-sm font-medium text-gray-900">{node.node_label}</div>
        <div className="text-xs text-gray-500">{node.node_type}</div>
      </div>
      <div className="flex space-x-1">
        <button
          onClick={() => handleStateChange(node.node_id, 'off')}
          className={`
            px-3 py-1.5 text-xs font-medium rounded transition-all
            ${
              node.state === 'off'
                ? 'bg-red-600 text-white shadow-md'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }
          `}
          title="關閉此節點"
        >
          OFF
        </button>
        <button
          onClick={() => handleStateChange(node.node_id, 'keep')}
          className={`
            px-3 py-1.5 text-xs font-medium rounded transition-all
            ${
              node.state === 'keep'
                ? 'bg-blue-600 text-white shadow-md'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }
          `}
          title="保持此節點"
        >
          KEEP
        </button>
        <button
          onClick={() => handleStateChange(node.node_id, 'emphasize')}
          className={`
            px-3 py-1.5 text-xs font-medium rounded transition-all
            ${
              node.state === 'emphasize'
                ? 'bg-yellow-600 text-white shadow-md'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }
          `}
          title="強調此節點"
        >
          EMPH
        </button>
      </div>
    </div>
  );

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="space-y-4">
        {groupBy === 'category' && nestedGroups
          ? Object.entries(nestedGroups).map(([category, typeGroups]) => (
              <div key={category} className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700 uppercase">{category}</h3>
                  <span className="text-xs text-gray-500">
                    {Object.values(typeGroups).flat().length} 個節點
                  </span>
                </div>
                {Object.entries(typeGroups).map(([nodeType, typeNodes]) => (
                  <div key={`${category}-${nodeType}`} className="ml-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-medium text-gray-600 capitalize">{nodeType}</h4>
                      <span className="text-xs text-gray-400">{typeNodes.length}</span>
                    </div>
                    <div className="space-y-1">
                      {typeNodes.map(renderNodeItem)}
                    </div>
                  </div>
                ))}
              </div>
            ))
          : Object.entries(groupedNodes).map(([group, groupNodes]) => (
              <div key={group} className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700 uppercase">{group}</h3>
                  <span className="text-xs text-gray-500">{groupNodes.length} 個節點</span>
                </div>
                <div className="space-y-1">
                  {groupNodes.map(renderNodeItem)}
                </div>
              </div>
            ))}
      </div>
    </div>
  );
}

