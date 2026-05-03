'use client';

import React, { useState, useRef, useEffect } from 'react';
import type { EffectiveLens } from '@/lib/lens-api';
import { getApiBaseUrl } from '@/lib/api-url';

type ChatMode = 'mirror' | 'experiment' | 'writeback';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

interface MindscapeChatPanelProps {
  effectiveLens: EffectiveLens | null;
  mode: ChatMode;
  sessionId: string;
  profileId: string;
  workspaceId?: string;
  selectedNodeIds?: string[];
}

export function MindscapeChatPanel({
  effectiveLens,
  mode,
  sessionId,
  profileId,
  workspaceId,
  selectedNodeIds = [],
}: MindscapeChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const getPresetPrompts = (): string[] => {
    if (mode === 'mirror') {
      return [
        'Summarize the current preset in three sentences.',
        'Show concrete examples for this node.',
        'Which node had the strongest impact across recent workspaces?',
      ];
    } else if (mode === 'experiment') {
      return [
        'Rewrite this caption with deep work off and rapid iteration emphasized.',
        'Create a stricter version with lower partner tolerance.',
      ];
    } else {
      return [
        'Show the experiment change summary.',
        'Apply these changes to the workspace.',
      ];
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${getApiBaseUrl()}/api/v1/mindscape/lens/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          message: input,
          profile_id: profileId,
          workspace_id: workspaceId,
          session_id: sessionId,
          effective_lens: effectiveLens,
          selected_node_ids: selectedNodeIds,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      const data = await response.json();
      const assistantMessage: ChatMessage = {
        id: `msg-${Date.now()}-assistant`,
        role: 'assistant',
        content: data.response || data.message || 'No response',
        timestamp: Date.now(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch {
      const errorMessage: ChatMessage = {
        id: `msg-${Date.now()}-error`,
        role: 'assistant',
        content: 'Failed to send the message.',
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePresetPrompt = (prompt: string) => {
    setInput(prompt);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8 text-sm text-gray-500">
            <div className="mb-4">
              {mode === 'mirror' && 'Mirror Mode'}
              {mode === 'experiment' && 'Experiment Mode'}
              {mode === 'writeback' && 'Writeback Mode'}
            </div>
            <div className="space-y-2">
              {getPresetPrompts().map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => handlePresetPrompt(prompt)}
                  className="block w-full text-left px-3 py-2 text-xs bg-gray-100 hover:bg-gray-200 rounded-md text-gray-700"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-3 py-2 text-sm text-gray-500">
              Thinking...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-200">
        <div className="flex space-x-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            rows={2}
            placeholder="Enter a message..."
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
