'use client';

import React, { useState } from 'react';
import { MessageItem } from '../MessageItem';
import { ChatMessage } from '@/hooks/useChatEvents';
import { SuggestionChip, type Suggestion } from './SuggestionChip';
import './MessageWithSuggestions.css';

interface MessageWithSuggestionsProps {
  message: ChatMessage;
  suggestions?: Suggestion[];
  onExecuteSuggestion: (suggestion: Suggestion) => void;
  workspaceId?: string;
  apiUrl?: string;
}

export function MessageWithSuggestions({
  message,
  suggestions,
  onExecuteSuggestion,
  workspaceId,
  apiUrl = ''
}: MessageWithSuggestionsProps) {
  const [executedIds, setExecutedIds] = useState<Set<string>>(new Set());
  const [projectConfirmed, setProjectConfirmed] = useState(false);
  const [showProjectSelector, setShowProjectSelector] = useState(false);

  const handleExecute = async (suggestion: Suggestion) => {
    await onExecuteSuggestion(suggestion);
    setExecutedIds(prev => new Set([...prev, suggestion.id]));
  };

  const projectAssignment = message.project_assignment;

  const handleConfirmProject = async () => {
    if (!projectAssignment?.project_id || !workspaceId) return;

    // TODO: Send confirmation to backend
    // For now, just mark as confirmed in UI
    setProjectConfirmed(true);
    setShowProjectSelector(false);
  };

  const handleCreateNewProject = async () => {
    // TODO: Create new project or navigate to project creation
    setShowProjectSelector(false);
  };

  const handleChangeProject = () => {
    setShowProjectSelector(true);
  };

  // Determine chip style based on confidence
  const getChipStyle = () => {
    if (!projectAssignment) return 'normal';
    if (projectAssignment.confidence >= 0.8) return 'normal';
    if (projectAssignment.confidence >= 0.5) return 'subtle';
    return 'warning';
  };

  const chipStyle = getChipStyle();

  return (
    <div className="message-with-suggestions">
      {/* Project Assignment Confirmation Prompt (assistive mode) */}
      {projectAssignment?.requires_ui_confirmation && !projectConfirmed && (
        <div className="mb-2 px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
          <div className="text-sm font-medium text-yellow-900 dark:text-yellow-100 mb-2">
            這次是延續「{projectAssignment.candidates?.[0]?.project?.title || projectAssignment.project_title || '現有專案'}」，還是要開始新的專案？
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleConfirmProject}
              className="px-3 py-1 text-xs bg-yellow-600 hover:bg-yellow-700 text-white rounded transition-colors"
            >
              延續現有專案
            </button>
            <button
              onClick={handleCreateNewProject}
              className="px-3 py-1 text-xs bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded transition-colors"
            >
              開始新專案
            </button>
          </div>
        </div>
      )}

      {/* Project Chip - Display current project */}
      {projectAssignment?.project_id && (
        <div className={`mb-2 px-2 py-1 text-xs rounded transition-colors ${
          chipStyle === 'normal'
            ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
            : chipStyle === 'subtle'
            ? 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 opacity-75'
            : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border border-yellow-300 dark:border-yellow-700'
        }`}>
          <div className="flex items-center justify-between gap-2">
            <span>
              正在為：{projectAssignment.project_title ||
                       projectAssignment.candidates?.[0]?.project?.title ||
                       projectAssignment.project_id} 工作
            </span>
            {chipStyle !== 'warning' && (
              <button
                onClick={handleChangeProject}
                className="text-xs underline hover:no-underline opacity-70 hover:opacity-100"
                title="更改專案"
              >
                更改
              </button>
            )}
          </div>
        </div>
      )}

      <MessageItem message={message} />

      {message.role === 'assistant' && suggestions && suggestions.length > 0 && (
        <div className="inline-suggestions">
          <div className="suggestions-header">
            <span className="title">Suggested Next Steps</span>
          </div>

          <div className="suggestions-list">
            {suggestions.map(suggestion => (
              <SuggestionChip
                key={suggestion.id}
                suggestion={suggestion}
                isExecuted={executedIds.has(suggestion.id)}
                onExecute={() => handleExecute(suggestion)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

