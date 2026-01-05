'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '../../lib/i18n';

import { getApiBaseUrl } from '../../lib/api-url';

const API_URL = getApiBaseUrl();

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  recommendedPlaybooks?: Array<{
    playbook_code: string;
    name: string;
    description: string;
    icon?: string;
  }>;
}

interface PlaybookDiscoveryChatProps {
  onPlaybookSelect?: (playbookCode: string) => void;
  selectedCapability?: string;
  selectedWorkspace?: string;
  currentPlaybookCode?: string;
}

export default function PlaybookDiscoveryChat({
  onPlaybookSelect,
  selectedCapability,
  selectedWorkspace,
  currentPlaybookCode
}: PlaybookDiscoveryChatProps) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'initial',
      role: 'assistant',
      content: t('tellMeYourNeeds'),
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Generate suggested questions based on context
  const suggestedQuestions = useMemo(() => {
    const baseQuestions = [
      '找：SEO 健檢',
      '這個 playbook 需要哪些工具？',
      '它在哪些 workspace 用過？'
    ];

    if (selectedCapability) {
      const capabilityName = selectedCapability.split('_').map(word =>
        word.charAt(0).toUpperCase() + word.slice(1)
      ).join(' ');
      baseQuestions.unshift(`在 ${capabilityName} 裡推薦一個最常用的`);
    }

    if (currentPlaybookCode) {
      baseQuestions.unshift(`這個 playbook 使用狀況怎麼樣？`);
    }

    return baseQuestions.slice(0, 4);
  }, [selectedCapability, currentPlaybookCode]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/playbooks/discover`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: userMessage.content,
          profile_id: 'default-user',
          capability_code: selectedCapability || undefined,
          workspace_id: selectedWorkspace || undefined
        })
      });

      if (response.ok) {
        const data = await response.json();
        let content = data.suggestion || t('basedOnYourNeeds');

        // Add recommended playbooks as clickable items
        if (data.recommended_playbooks && data.recommended_playbooks.length > 0) {
          content += '\n\n' + t('recommendedPlaybooks') + '\n';
          data.recommended_playbooks.forEach((pb: any, index: number) => {
            content += `\n${index + 1}. ${pb.icon || '📋'} ${pb.name}`;
          });
        }

        const assistantMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: content,
          timestamp: new Date(),
          recommendedPlaybooks: data.recommended_playbooks || []
        };
        setMessages(prev => [...prev, assistantMessage]);
      } else {
        throw new Error('Failed to get suggestion');
      }
    } catch (err) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: t('sorryCannotProcess'),
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 mb-4">
        {messages.map((message) => (
          <div key={message.id} className="space-y-2">
            <div
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap ${
                  message.role === 'user'
                    ? 'bg-blue-600 dark:bg-blue-700 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200'
                }`}
              >
                {message.content}
              </div>
            </div>
            {message.role === 'assistant' && message.recommendedPlaybooks && message.recommendedPlaybooks.length > 0 && (
              <div className="space-y-2">
                {message.recommendedPlaybooks.map((pb) => (
                  <button
                    key={pb.playbook_code}
                      onClick={() => {
                        if (onPlaybookSelect) {
                          onPlaybookSelect(pb.playbook_code);
                        } else {
                          const scrollY = window.scrollY;
                          router.push(`/playbooks/${pb.playbook_code}`);
                          // Restore scroll position after navigation
                          setTimeout(() => {
                            window.scrollTo(0, scrollY);
                          }, 0);
                        }
                      }}
                    className="w-full text-left p-2 bg-surface-secondary dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:border-accent dark:hover:border-blue-600 hover:bg-accent-10 dark:hover:bg-blue-900/20 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      {pb.icon && <span className="text-lg flex-shrink-0">{pb.icon}</span>}
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                          {pb.name}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mt-0.5">
                          {pb.description}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
              <span className="inline-block animate-pulse">思考中...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 pt-3">
        {/* Suggested Questions Chips */}
        {messages.length === 1 && suggestedQuestions.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {suggestedQuestions.map((question, idx) => (
              <button
                key={idx}
                onClick={async () => {
                  if (isLoading) return;

                  const userMessage: Message = {
                    id: Date.now().toString(),
                    role: 'user',
                    content: question,
                    timestamp: new Date()
                  };

                  setMessages(prev => [...prev, userMessage]);
                  setIsLoading(true);

                  try {
                    const apiUrl = API_URL.startsWith('http') ? API_URL : '';
                    const response = await fetch(`${apiUrl}/api/v1/playbooks/discover`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                      },
                      body: JSON.stringify({
                        query: question,
                        profile_id: 'default-user'
                      })
                    });

                    if (response.ok) {
                      const data = await response.json();
                      let content = data.suggestion || t('basedOnYourNeeds');

                      if (data.recommended_playbooks && data.recommended_playbooks.length > 0) {
                        content += '\n\n' + t('recommendedPlaybooks') + '\n';
                        data.recommended_playbooks.forEach((pb: any, index: number) => {
                          content += `\n${index + 1}. ${pb.icon || '📋'} ${pb.name}`;
                        });
                      }

                      const assistantMessage: Message = {
                        id: (Date.now() + 1).toString(),
                        role: 'assistant',
                        content: content,
                        timestamp: new Date(),
                        recommendedPlaybooks: data.recommended_playbooks || []
                      };
                      setMessages(prev => [...prev, assistantMessage]);
                    } else {
                      throw new Error('Failed to get suggestion');
                    }
                  } catch (err) {
                    const errorMessage: Message = {
                      id: (Date.now() + 1).toString(),
                      role: 'assistant',
                      content: t('sorryCannotProcess'),
                      timestamp: new Date()
                    };
                    setMessages(prev => [...prev, errorMessage]);
                  } finally {
                    setIsLoading(false);
                  }
                }}
                disabled={isLoading}
                className="px-3 py-1.5 text-xs bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-full hover:bg-accent-10 dark:hover:bg-blue-900/20 hover:border-accent dark:hover:border-blue-600 transition-colors text-primary dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {question}
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={t('describeYourNeeds')}
            className="flex-1 px-3 py-2 text-xs border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 text-xs bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
                  {t('send')}
          </button>
        </div>
      </div>
    </div>
  );
}

