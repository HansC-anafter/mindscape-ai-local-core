'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '@/lib/i18n';
import WorkspaceModeSelector, { WorkspaceMode } from '../../../components/WorkspaceModeSelector';
import ActivePlaybookIndicator from '../../../components/ActivePlaybookIndicator';

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
  associatedIntent?: AssociatedIntent | null;
  workspaceId: string;
  onModeChange?: (mode: WorkspaceMode) => void;
  updatingMode?: boolean;
  onWorkspaceUpdate?: () => void;
  apiUrl?: string;
}

const modeLabels: Record<NonNullable<WorkspaceMode>, string> = {
  research: '研究模式',
  publishing: '發佈模式',
  planning: '規劃模式',
};

const modeColors: Record<NonNullable<WorkspaceMode>, string> = {
  research: 'bg-blue-100 text-blue-700 border-blue-300',
  publishing: 'bg-green-100 text-green-700 border-green-300',
  planning: 'bg-purple-100 text-purple-700 border-purple-300',
};

export default function WorkspaceHeader({
  workspaceName,
  mode,
  associatedIntent,
  workspaceId,
  onModeChange,
  updatingMode = false,
  onWorkspaceUpdate,
  apiUrl = 'http://localhost:8000',
}: WorkspaceHeaderProps) {
  const router = useRouter();
  const [isEditing, setIsEditing] = useState(false);
  const [editedName, setEditedName] = useState(workspaceName);
  const [isRenaming, setIsRenaming] = useState(false);

  // Update editedName when workspaceName changes
  React.useEffect(() => {
    if (!isEditing) {
      setEditedName(workspaceName);
    }
  }, [workspaceName, isEditing]);

  const handleSwitchIntent = () => {
    // TODO: Open intent selector modal
    console.log('Switch intent');
  };

  const handleViewInMindscape = () => {
    if (associatedIntent?.id) {
      router.push(`/mindscape?intent=${associatedIntent.id}`);
    }
  };

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
        alert(errorData.detail || t('workspaceRenameFailed'));
        setEditedName(workspaceName);
      }
    } catch (err) {
      console.error('Failed to rename workspace:', err);
      alert(t('workspaceRenameFailed'));
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
      <div className="bg-white border-b border-gray-200 px-6 py-1.5">
        <div className="flex items-center gap-4 relative">
          {/* Left: Workspace name (moved from center to left, where "默默 AI 工作台" was) */}
          <div className="flex items-center flex-shrink-0">
            {isEditing ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={handleKeyPress}
                onBlur={handleSaveRename}
                disabled={isRenaming}
                className="text-base font-semibold text-gray-900 bg-white border border-blue-500 rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoFocus
              />
            ) : (
              <div className="flex items-center gap-1.5 group">
                <h1 className="text-base font-semibold text-gray-900">
                  {workspaceName}
                </h1>
                <button
                  onClick={handleStartRename}
                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600 text-xs"
                  title={t('workspaceRename')}
                >
                  ✏️
                </button>
              </div>
            )}
          </div>

          {/* Center: Active Playbook Indicator (centered) */}
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
