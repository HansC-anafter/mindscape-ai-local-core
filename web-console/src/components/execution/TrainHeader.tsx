'use client';

import React from 'react';
import { usePathname, useRouter } from 'next/navigation';

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
  workspaceId?: string;
  onBackToWorkspace?: () => void;
}

function getStatusIcon(status: ExecutionStep['status']): string {
  switch (status) {
    case 'completed': return 'DONE';
    case 'in_progress': return 'RUN';
    case 'pending': return 'WAIT';
    case 'error': return 'ERR';
    default: return 'IDLE';
  }
}

export default function TrainHeader({
  workspaceName,
  workspaceBadges,
  steps,
  progress,
  isExecuting,
  onWorkspaceNameEdit,
  workspaceId,
  onBackToWorkspace,
}: TrainHeaderProps) {
  const pathname = usePathname();
  const router = useRouter();

  const isExecutionPage = pathname?.includes('/executions/');

  const handleBackToWorkspace = () => {
    if (onBackToWorkspace) {
      onBackToWorkspace();
    } else if (workspaceId) {
      router.push(`/workspaces/${workspaceId}`);
    }
  };

  return (
    <div className="train-header relative w-full h-12 overflow-hidden" style={{ background: 'rgba(139, 92, 246, 0.03)' }}>
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

      <div className="relative z-10 flex items-center h-full px-4 gap-0 overflow-x-auto">
        {isExecutionPage && (workspaceId || onBackToWorkspace) && (
          <button
            onClick={handleBackToWorkspace}
            className="flex items-center gap-1.5 px-2 py-1 text-sm text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded transition-colors flex-shrink-0 mr-2"
            title="Back to Workspace Chat"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span className="text-xs">Workspace Chat</span>
          </button>
        )}

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={onWorkspaceNameEdit}
            className="group flex items-center gap-1.5"
          >
            <h1 className="text-base font-semibold text-primary dark:text-gray-100 whitespace-nowrap">
              {workspaceName}
            </h1>
            {onWorkspaceNameEdit && (
              <span className="opacity-0 group-hover:opacity-100 text-tertiary dark:text-gray-500 text-xs transition-opacity">
                Edit
              </span>
            )}
          </button>
          {workspaceBadges && workspaceBadges.length > 0 && (
            <span className="text-sm">{workspaceBadges.join('')}</span>
          )}
        </div>

        {steps.length > 0 && (
          <span className="mx-2 text-sm flex-shrink-0" style={{ color: 'rgba(139, 92, 246, 0.3)' }}>--</span>
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
                <span className="text-xs font-medium text-primary dark:text-gray-300 whitespace-nowrap">
                  {step.name}
                </span>
                {step.detail && (
                  <span className="text-[10px] text-secondary">{step.detail}</span>
                )}
              </div>
              <span className="text-sm">{step.icon}</span>
            </div>
            {i < steps.length - 1 && (
              <span className="mx-2 text-sm flex-shrink-0" style={{ color: 'rgba(139, 92, 246, 0.3)' }}>--</span>
            )}
          </React.Fragment>
        ))}

        {progress === 100 && steps.length > 0 && (
          <span
            className="ml-3 text-sm flex-shrink-0"
            style={{
              color: 'rgba(139, 92, 246, 0.9)',
              animation: 'fadeIn 0.5s ease'
            }}
          >
            Complete
          </span>
        )}
      </div>

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
