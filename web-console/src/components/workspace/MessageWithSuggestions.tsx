'use client';

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { ChatMessage } from '@/hooks/useChatEvents';
import { SuggestionChip, type Suggestion } from './SuggestionChip';
import './MessageWithSuggestions.css';

const MessageItem = dynamic(
  () => import('../MessageItem').then((module) => module.MessageItem),
  { ssr: false, loading: () => <div className="text-xs text-secondary">Loading...</div> }
);

interface MessageWithSuggestionsProps {
  message: ChatMessage;
  suggestions?: Suggestion[];
  onExecuteSuggestion: (suggestion: Suggestion) => void;
  onRetry?: (retryData: { message: string; agent_id?: string }) => void;
  workspaceId?: string;
  apiUrl?: string;
}

export function MessageWithSuggestions({
  message,
  suggestions,
  onExecuteSuggestion,
  onRetry,
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

    setProjectConfirmed(true);
    setShowProjectSelector(false);
  };

  const handleCreateNewProject = async () => {
    setShowProjectSelector(false);
  };

  const handleChangeProject = () => {
    setShowProjectSelector(true);
  };

  const getChipStyle = () => {
    if (!projectAssignment) return 'normal';
    if (projectAssignment.confidence >= 0.8) return 'normal';
    if (projectAssignment.confidence >= 0.5) return 'subtle';
    return 'warning';
  };

  const chipStyle = getChipStyle();
  const projectTitle = projectAssignment?.candidates?.[0]?.project?.title ||
    projectAssignment?.project_title ||
    'the current project';

  return (
    <div className="message-with-suggestions">
      {projectAssignment?.requires_ui_confirmation && !projectConfirmed && (
        <div className="mb-2 px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
          <div className="text-sm font-medium text-yellow-900 dark:text-yellow-100 mb-2">
            Continue {projectTitle} or start a new project?
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleConfirmProject}
              className="px-3 py-1 text-xs bg-yellow-600 hover:bg-yellow-700 text-white rounded transition-colors"
            >
              Continue Current Project
            </button>
            <button
              onClick={handleCreateNewProject}
              className="px-3 py-1 text-xs bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded transition-colors"
            >
              Start New Project
            </button>
          </div>
        </div>
      )}

      {projectAssignment?.project_id && (
        <div className={`mb-2 px-2 py-1 text-xs rounded transition-colors ${chipStyle === 'normal'
            ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
            : chipStyle === 'subtle'
              ? 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 opacity-75'
              : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border border-yellow-300 dark:border-yellow-700'
          }`}>
          <div className="flex items-center justify-between gap-2">
            <span>
              Working on: {projectAssignment.project_title ||
                projectAssignment.candidates?.[0]?.project?.title ||
                projectAssignment.project_id}
            </span>
            {chipStyle !== 'warning' && (
              <button
                onClick={handleChangeProject}
                className="text-xs underline hover:no-underline opacity-70 hover:opacity-100"
                title="Change project"
              >
                Change
              </button>
            )}
          </div>
        </div>
      )}

      <MessageItem message={message} onRetry={onRetry} />

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
