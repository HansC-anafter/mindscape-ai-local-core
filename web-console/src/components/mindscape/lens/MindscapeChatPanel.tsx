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

  // 根据模式生成预设提示
  const getPresetPrompts = (): string[] => {
    if (mode === 'mirror') {
      return [
        '總結目前這個 Preset 的核心氣質，用三句話形容。',
        '這顆節點有哪些具體例子？',
        '從最近 10 個 Workspace 看，你覺得有哪顆節點實際影響最大？',
      ];
    } else if (mode === 'experiment') {
      return [
        '如果我把「深度工作」關掉、改成「快速試錯」，請幫我用新的 Lens 重寫這篇 IG caption 看看。',
        '幫我開一個「更狠一點」的版本，把合作對象容忍度降 20%。',
      ];
    } else {
      return [
        '顯示這次實驗的變更摘要',
        '將變更套用到 Workspace',
      ];
    }
  };

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 发送消息
  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('' as any);
    setIsLoading(true);

    try {
      // 调用后端 API
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
        content: data.response || data.message || '無回應',
        timestamp: Date.now(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage: ChatMessage = {
        id: `msg-${Date.now()}-error`,
        role: 'assistant',
        content: '抱歉，發送訊息時發生錯誤。',
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // 使用预设提示
  const handlePresetPrompt = (prompt: string) => {
    setInput(prompt);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8 text-sm text-gray-500">
            <div className="mb-4">
              {mode === 'mirror' && '🪞 看見自己'}
              {mode === 'experiment' && '🎚 調色實驗'}
              {mode === 'writeback' && '📦 寫回 Workspace'}
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
              思考中...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
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
            placeholder="輸入訊息..."
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium"
          >
            發送
          </button>
        </div>
      </div>
    </div>
  );
}

