'use client';

import React from 'react';

export interface ExecutionStep {
  id: string;
  name: string;
  icon: string;
  status: 'completed' | 'in_progress' | 'pending' | 'error';
  detail?: string;
  artifactType?: string;
}

interface TrainHeaderProps {
  workspaceName: string;
  workspaceBadges?: string[];
  steps: ExecutionStep[];
  progress: number;
  isExecuting: boolean;
  onWorkspaceNameEdit?: () => void;
}

function getStatusIcon(status: ExecutionStep['status']): string {
  switch (status) {
    case 'completed': return '✅';
    case 'in_progress': return '🔄';
    case 'pending': return '⏳';
    case 'error': return '❌';
    default: return '○';
  }
}

export default function TrainHeader({
  workspaceName,
  workspaceBadges,
  steps,
  progress,
  isExecuting,
  onWorkspaceNameEdit,
}: TrainHeaderProps) {
  return (
    <div className="train-header relative w-full h-12 overflow-hidden" style={{ background: 'rgba(139, 92, 246, 0.03)' }}>
      {/* Progress bar background */}
      {isExecuting && (
        <div
          className="absolute top-0 left-0 h-full transition-all duration-400 ease-out"
          style={{
            width: `${progress}%`,
            background: 'rgba(139, 92, 246, 0.12)',
            transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)'
          }}
        />
      )}

      {/* Foreground content */}
      <div className="relative z-10 flex items-center h-full px-4 gap-0 overflow-x-auto">
        {/* Workspace title */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={onWorkspaceNameEdit}
            className="group flex items-center gap-1.5"
          >
            <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">
              {workspaceName}
            </h1>
            {onWorkspaceNameEdit && (
              <span className="opacity-0 group-hover:opacity-100 text-gray-400 dark:text-gray-500 text-xs transition-opacity">
                ✏️
              </span>
            )}
          </button>
          {workspaceBadges && workspaceBadges.length > 0 && (
            <span className="text-sm">{workspaceBadges.join('')}</span>
          )}
        </div>

        {/* Connector + Task wagons */}
        {steps.length > 0 && (
          <span className="mx-2 text-sm flex-shrink-0" style={{ color: 'rgba(139, 92, 246, 0.3)' }}>━━</span>
        )}

        {steps.map((step, i) => (
          <React.Fragment key={step.id}>
            <div
              className={`train-stop flex flex-col items-center gap-0.5 flex-shrink-0 ${
                step.status === 'pending' ? 'opacity-50' : 'opacity-100'
              } ${step.status === 'error' ? 'text-red-500' : ''}`}
              style={{
                animation: 'slideIn 0.3s ease',
              }}
            >
              <div className="flex items-center gap-1">
                <span className="text-sm">{getStatusIcon(step.status)}</span>
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
                  {step.name}
                </span>
                {step.detail && (
                  <span className="text-[10px] text-gray-500">{step.detail}</span>
                )}
              </div>
              <span className="text-sm">{step.icon}</span>
            </div>
            {i < steps.length - 1 && (
              <span className="mx-2 text-sm flex-shrink-0" style={{ color: 'rgba(139, 92, 246, 0.3)' }}>━━</span>
            )}
          </React.Fragment>
        ))}

        {/* Completion mark */}
        {progress === 100 && steps.length > 0 && (
          <span
            className="ml-3 text-sm flex-shrink-0"
            style={{
              color: 'rgba(139, 92, 246, 0.9)',
              animation: 'fadeIn 0.5s ease'
            }}
          >
            ✨ 完成！
          </span>
        )}
      </div>

      {/* Animations */}
      <style jsx>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-12px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

