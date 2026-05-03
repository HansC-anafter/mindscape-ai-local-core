'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';
import type { WorkspaceMode } from '../../../components/WorkspaceModeSelector';
import ActivePlaybookIndicator from '../../../components/ActivePlaybookIndicator';
import ExecutionModePill, { ExecutionMode, ExecutionPriority } from '../../../components/ExecutionModePill';
import ExpectedArtifactsBadge from '../../../components/ExpectedArtifactsBadge';
import { getApiBaseUrl } from '../../../lib/api-url';

interface AssociatedIntent {
  id: string;
  title: string;
  tags?: string[];
  status?: string;
  priority?: string;
}

interface WorkspaceHeaderProps {
  workspaceName: string;
  mode: WorkspaceMode;
  executionMode?: ExecutionMode;
  executionPriority?: ExecutionPriority;
  expectedArtifacts?: string[];
  associatedIntent?: AssociatedIntent | null;
  workspaceId: string;
  onModeChange?: (mode: WorkspaceMode) => void;
  onExecutionModeClick?: () => void;
  updatingMode?: boolean;
  onWorkspaceUpdate?: () => void;
  apiUrl?: string;
}

export default function WorkspaceHeader({
  workspaceName,
  executionMode,
  executionPriority,
  expectedArtifacts,
  workspaceId,
  onExecutionModeClick,
  onWorkspaceUpdate,
  apiUrl = getApiBaseUrl(),
}: WorkspaceHeaderProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedName, setEditedName] = useState(workspaceName);
  const [isRenaming, setIsRenaming] = useState(false);

  React.useEffect(() => {
    if (!isEditing) {
      setEditedName(workspaceName);
    }
  }, [workspaceName, isEditing]);

  const handleStartRename = () => {
    setIsEditing(true);
    setEditedName(workspaceName);
  };

  const handleCancelRename = () => {
    setIsEditing(false);
    setEditedName(workspaceName);
  };

  const handleSaveRename = async () => {
    if (!editedName.trim() || editedName.trim() === workspaceName) {
      handleCancelRename();
      return;
    }

    setIsRenaming(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: editedName.trim() }),
      });

      if (response.ok) {
        setIsEditing(false);
        if (onWorkspaceUpdate) {
          onWorkspaceUpdate();
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(errorData.detail || t('workspaceRenameFailed' as any));
        setEditedName(workspaceName);
      }
    } catch (err) {
      console.error('Failed to rename workspace:', err);
      alert(t('workspaceRenameFailed' as any));
      setEditedName(workspaceName);
    } finally {
      setIsRenaming(false);
    }
  };


  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSaveRename();
    } else if (e.key === 'Escape') {
      handleCancelRename();
    }
  };

  return (
    <>
      <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-1.5">
        <div className="flex items-center gap-4 relative">
          <div className="flex items-center gap-3 flex-shrink-0">
            {isEditing ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={handleKeyPress}
                onBlur={handleSaveRename}
                disabled={isRenaming}
                className="text-base font-semibold text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 border border-blue-500 dark:border-blue-600 rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                autoFocus
              />
            ) : (
              <div className="flex items-center gap-1.5 group">
                <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  {workspaceName}
                </h1>
                <button
                  onClick={handleStartRename}
                  className="opacity-0 group-hover:opacity-100 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-xs"
                  title={t('workspaceRename' as any)}
                >
                  Rename
                </button>
              </div>
            )}

            <ExecutionModePill
              mode={executionMode || 'hybrid'}
              priority={executionPriority}
              onClick={onExecutionModeClick}
            />

            {expectedArtifacts && expectedArtifacts.length > 0 && (
              <ExpectedArtifactsBadge artifacts={expectedArtifacts} />
            )}
          </div>

          <div className="absolute left-1/2 transform -translate-x-1/2">
            <ActivePlaybookIndicator
              workspaceId={workspaceId}
              apiUrl={apiUrl}
            />
          </div>

        </div>
      </div>
    </>
  );
}
