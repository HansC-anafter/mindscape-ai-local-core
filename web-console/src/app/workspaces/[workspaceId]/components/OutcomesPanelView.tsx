import React from 'react';

import ConflictDialog from '@/components/ConflictDialog';
import { t } from '@/lib/i18n';

import SandboxModalWrapper from '../../components/execution-inspector/SandboxModalWrapper';
import { buildCapabilityComponentUrl } from './outcomesPanelApi';
import {
  getArtifactIcon,
  resolveArtifactDisplayInfo,
} from './outcomesPanelState';
import type {
  Artifact,
  MatchingCapabilityComponent,
  SandboxModalState,
} from './outcomesPanelTypes';

interface OutcomesPanelViewProps {
  artifacts: Artifact[];
  conflictDialog: any;
  error: string | null;
  highlightedArtifactIds: Set<string>;
  loading: boolean;
  matchingComponents: MatchingCapabilityComponent[];
  sandboxModal: SandboxModalState;
  ToastComponent: React.ComponentType;
  workspaceId: string;
  onArtifactFileClick: (artifact: Artifact, event: React.MouseEvent) => void;
  onCloseSandbox: () => void;
  onOpenExternal: (artifact: Artifact, event: React.MouseEvent) => void;
  onSandboxClick: (artifact: Artifact, event: React.MouseEvent) => void;
}

export function OutcomesPanelView({
  artifacts,
  conflictDialog,
  error,
  highlightedArtifactIds,
  loading,
  matchingComponents,
  sandboxModal,
  ToastComponent,
  workspaceId,
  onArtifactFileClick,
  onCloseSandbox,
  onOpenExternal,
  onSandboxClick,
}: OutcomesPanelViewProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-gray-500 dark:text-gray-400">{t('loading' as any) || 'Loading...'}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-red-500 dark:text-red-400">{t('error' as any) || 'Error'}: {error}</div>
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full px-2">
        <div className="text-xs text-gray-500 dark:text-gray-400">{t('noOutcomes' as any) || 'No outcomes yet'}</div>
      </div>
    );
  }

  return (
    <>
      <ToastComponent />

      {conflictDialog && (
        <ConflictDialog
          isOpen={conflictDialog.isOpen}
          conflict={conflictDialog.conflict}
          onConfirm={conflictDialog.onConfirm}
          onCancel={conflictDialog.onCancel}
          onUseNewVersion={conflictDialog.onUseNewVersion}
        />
      )}

      {matchingComponents.map((component) => (
        <div key={component.key} className="p-2 border-b border-gray-200 dark:border-gray-700">
          <a
            href={buildCapabilityComponentUrl(workspaceId, component.capabilityCode, component.componentCode)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors text-sm font-medium"
          >
            <span>{component.description || `View ${component.componentCode}`}</span>
          </a>
        </div>
      ))}

      <div className="h-full overflow-y-auto p-2 space-y-2">
        {artifacts.map((artifact) => {
          const isHighlighted = highlightedArtifactIds.has(artifact.id);
          const display = resolveArtifactDisplayInfo(artifact);

          return (
            <div
              key={artifact.id}
              className={`
              bg-surface-secondary dark:bg-gray-800 border rounded-lg p-2.5 hover:border-accent dark:hover:border-blue-600 hover:shadow-md transition-all
              ${isHighlighted
                  ? 'border-accent dark:border-blue-500 shadow-lg bg-accent-10 dark:bg-blue-900/20 animate-pulse'
                  : 'border-default dark:border-gray-700'
                }
            `}
              style={isHighlighted ? {
                animation: 'fadeInHighlight 0.5s ease-in-out',
              } : undefined}
            >
              <div
                onClick={(event) => onArtifactFileClick(artifact, event)}
                className="flex items-center gap-2 mb-1 cursor-pointer group"
              >
                <span className="text-base flex-shrink-0">{getArtifactIcon(artifact.artifact_type)}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm text-primary dark:text-gray-100 truncate group-hover:text-accent dark:group-hover:text-blue-400 transition-colors">
                    {display.fileName}
                  </div>
                </div>
                {artifact.primary_action_type === 'download' && display.filePath && (
                  <button
                    onClick={(event) => onOpenExternal(artifact, event)}
                    className="px-2 py-0.5 text-[10px] bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-400 rounded hover:opacity-80 dark:hover:bg-blue-900/40 transition-colors flex-shrink-0"
                    title="Download File"
                  >
                    <span>Download</span>
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between text-[10px] text-gray-400 dark:text-gray-500">
                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                  <span className="truncate">{artifact.playbook_code}</span>
                  <span>-</span>
                  <span className="flex-shrink-0">{display.formattedDate}</span>
                </div>
                {(display.filePath || display.executionId) && (
                  <button
                    onClick={(event) => onSandboxClick(artifact, event)}
                    className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 hover:underline flex-shrink-0 ml-2 px-1 py-0.5 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 transition-colors"
                    title="View in Sandbox"
                  >
                    Sandbox
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <style jsx global>{`
        @keyframes fadeInHighlight {
          0% {
            opacity: 0;
            transform: translateY(-10px) scale(0.98);
            background-color: rgba(59, 130, 246, 0.1);
          }
          50% {
            background-color: rgba(59, 130, 246, 0.2);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
            background-color: rgba(239, 246, 255, 1);
          }
        }
      `}</style>

      {sandboxModal.show && sandboxModal.sandboxId && sandboxModal.executionId && (
        <SandboxModalWrapper
          isOpen={sandboxModal.show}
          onClose={onCloseSandbox}
          workspaceId={workspaceId}
          sandboxId={sandboxModal.sandboxId}
          executionId={sandboxModal.executionId}
          initialFile={sandboxModal.initialFile || undefined}
        />
      )}
    </>
  );
}
