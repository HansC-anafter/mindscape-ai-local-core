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
}

export function MessageWithSuggestions({
  message,
  suggestions,
  onExecuteSuggestion
}: MessageWithSuggestionsProps) {
  const [executedIds, setExecutedIds] = useState<Set<string>>(new Set());

  const handleExecute = async (suggestion: Suggestion) => {
    await onExecuteSuggestion(suggestion);
    setExecutedIds(prev => new Set([...prev, suggestion.id]));
  };

  return (
    <div className="message-with-suggestions">
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

