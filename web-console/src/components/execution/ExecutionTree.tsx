'use client';

import React from 'react';

export interface TreeStep {
  id: string;
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  detail?: string;
  children?: TreeStep[];
}

interface ExecutionTreeProps {
  steps: TreeStep[];
  isCollapsed?: boolean;
  onToggle?: () => void;
  onStepClick?: (stepId: string) => void;
}

function getStatusIcon(status: TreeStep['status']): string {
  switch (status) {
    case 'completed': return '✅';
    case 'in_progress': return '🔄';
    case 'error': return '❌';
    case 'pending':
    default: return '○';
  }
}

function getStatusColor(status: TreeStep['status']): string {
  switch (status) {
    case 'completed': return 'text-green-600 dark:text-green-400';
    case 'in_progress': return 'text-blue-600 dark:text-blue-400';
    case 'error': return 'text-red-600 dark:text-red-400';
    case 'pending':
    default: return 'text-gray-400 dark:text-gray-500';
  }
}

const TreeNode: React.FC<{
  step: TreeStep;
  depth: number;
  onStepClick?: (stepId: string) => void;
}> = ({ step, depth, onStepClick }) => {
  const paddingLeft = depth * 16;

  return (
    <div className="select-none">
      <div
        className={`
          flex items-center gap-2 py-1 px-2 rounded-md
          hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors
          ${onStepClick ? 'cursor-pointer' : ''}
          ${step.status === 'in_progress' ? 'bg-purple-50/50 dark:bg-purple-900/20' : ''}
        `}
        style={{ paddingLeft }}
        onClick={() => onStepClick?.(step.id)}
      >
        {/* Status icon */}
        <span className={`text-xs ${step.status === 'in_progress' ? 'animate-spin' : ''}`}>
          {getStatusIcon(step.status)}
        </span>

        {/* Step name */}
        <span className={`text-xs font-medium ${getStatusColor(step.status)}`}>
          {step.name}
        </span>

        {/* Detail badge */}
        {step.detail && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500 ml-auto">
            {step.detail}
          </span>
        )}
      </div>

      {/* Children */}
      {step.children && step.children.length > 0 && (
        <div className="border-l border-gray-200 dark:border-gray-700 ml-4">
          {step.children.map((child) => (
            <TreeNode
              key={child.id}
              step={child}
              depth={depth + 1}
              onStepClick={onStepClick}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const ExecutionTree: React.FC<ExecutionTreeProps> = ({
  steps,
  isCollapsed = false,
  onToggle,
  onStepClick,
}) => {
  const hasSteps = steps.length > 0;
  const inProgressCount = steps.filter(s => s.status === 'in_progress').length;
  const completedCount = steps.filter(s => s.status === 'completed').length;

  return (
    <div className="border-b dark:border-gray-700">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-500 text-xs">{isCollapsed ? '▶' : '▼'}</span>
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            執行中
          </span>
          {hasSteps && (
            <span className="text-[10px] text-gray-400">
              {completedCount}/{steps.length}
            </span>
          )}
        </div>

        {/* Status indicator */}
        {inProgressCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-blue-500">
            <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
            進行中
          </span>
        )}
      </div>

      {/* Content */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[400px] opacity-100'
        }`}
      >
        <div className="pb-2">
          {hasSteps ? (
            <div className="px-1">
              {steps.map((step) => (
                <TreeNode
                  key={step.id}
                  step={step}
                  depth={0}
                  onStepClick={onStepClick}
                />
              ))}
            </div>
          ) : (
            <div className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500 italic">
              目前沒有執行中的 Playbook
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExecutionTree;

