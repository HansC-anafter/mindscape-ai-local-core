'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '../../../lib/i18n';
import { useSettingsContext, type SettingsContext } from '../hooks/useSettingsContext';
import type { SettingsTab } from '../types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  actions?: Array<{
    label: string;
    action: string;
    params?: Record<string, any>;
  }>;
}

interface SettingsConfigAssistantProps {
  currentTab: SettingsTab;
  currentSection?: string;
  onNavigate?: (tab: SettingsTab, section?: string) => void;
}

export function SettingsConfigAssistant({
  currentTab,
  currentSection,
  onNavigate,
}: SettingsConfigAssistantProps) {
  const router = useRouter();
  const { context } = useSettingsContext(currentTab, currentSection);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const generateWelcomeMessage = useCallback((ctx: SettingsContext | null): string => {
    if (!ctx) {
      return t('configAssistantWelcome') || 'Welcome to Configuration Assistant! How can I help you?';
    }

    const { configSnapshot } = ctx;
    const issues: string[] = [];

    if (!configSnapshot.backend.openai_configured && !configSnapshot.backend.anthropic_configured) {
      issues.push(t('configAssistantIssueNoLLM') || 'No LLM API keys configured');
    }

    if (configSnapshot.tools.issues.length > 0) {
      issues.push(`${configSnapshot.tools.issues.length} ${t('configAssistantIssueTools') || 'tools not connected'}`);
    }

    if (configSnapshot.services.issues.length > 0) {
      issues.push(`${configSnapshot.services.issues.length} ${t('configAssistantIssueServices') || 'service issues'}`);
    }

    let welcome = t('configAssistantWelcome') || 'Welcome! I can help you with:';
    welcome += '\n- ' + (t('configAssistantHelpLLM') || 'Configure LLM API keys');
    welcome += '\n- ' + (t('configAssistantHelpTools') || 'Connect tools and services');
    welcome += '\n- ' + (t('configAssistantHelpDiagnose') || 'Diagnose configuration issues');
    welcome += '\n- ' + (t('configAssistantHelpAnswer') || 'Answer configuration questions');

    if (issues.length > 0) {
      welcome += `\n\n${t('configAssistantDetectedIssues') || 'Detected issues'}: ${issues.join(', ')}`;
    }

    return welcome;
  }, []);

  useEffect(() => {
    if (context && messages.length === 0) {
      const welcomeMessage = generateWelcomeMessage(context);
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: welcomeMessage,
        timestamp: new Date()
      }]);
    }
  }, [context, generateWelcomeMessage, messages.length]);

  const buildSystemPrompt = useCallback((ctx: SettingsContext | null): string => {
    if (!ctx) {
      return 'You are a configuration assistant for Mindscape AI. Help users configure their system.';
    }

    const { configSnapshot, currentTab, currentSection } = ctx;

    return `You are a configuration assistant for Mindscape AI.

Current Context:
- Current Page: ${currentTab}${currentSection ? ` > ${currentSection}` : ''}
- Backend Mode: ${configSnapshot.backend.mode}
- LLM Status: ${configSnapshot.backend.openai_configured ? 'OpenAI configured' : 'OpenAI not configured'}${configSnapshot.backend.anthropic_configured ? ', Anthropic configured' : ', Anthropic not configured'}
- Tools: ${configSnapshot.tools.connected}/${configSnapshot.tools.total} connected
- Services: Backend ${configSnapshot.services.backend}, LLM ${configSnapshot.services.llm}, Vector DB ${configSnapshot.services.vector_db}
${configSnapshot.services.issues.length > 0 ? `- Issues: ${configSnapshot.services.issues.map(i => i.message).join(', ')}` : ''}

Your role:
1. Provide contextual help based on current page and configuration status
2. Suggest next steps to complete configuration
3. Answer questions about configuration
4. Provide quick action buttons to navigate to relevant settings

Be concise, helpful, and action-oriented.`;
  }, []);

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
      const systemPrompt = buildSystemPrompt(context);

      const response = await fetch(`${API_URL}/api/v1/system-settings/assistant/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage.content,
          context: {
            current_tab: currentTab,
            current_section: currentSection,
            config_snapshot: context?.configSnapshot,
          },
          system_prompt: systemPrompt,
        })
      });

      if (response.ok) {
        const data = await response.json();
        const assistantMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: data.response || data.message || t('configAssistantError') || 'Sorry, I could not process your request.',
          timestamp: new Date(),
          actions: data.actions || []
        };
        setMessages(prev => [...prev, assistantMessage]);
      } else if (response.status === 404 || response.status === 501) {
        // Backend API not implemented yet, provide fallback response
        const fallbackMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: t('configAssistantFallback') || 'The assistant API is not yet available. Based on your current configuration, I can help you navigate to the right settings. What would you like to configure?',
          timestamp: new Date(),
          actions: [
            {
              label: t('basicSettings') || 'Basic Settings',
              action: 'navigate',
              params: { tab: 'basic' }
            },
            {
              label: t('toolsAndIntegrations') || 'Tools & Integrations',
              action: 'navigate',
              params: { tab: 'tools' }
            }
          ]
        };
        setMessages(prev => [...prev, fallbackMessage]);
      } else {
        throw new Error('Failed to get response');
      }
    } catch (err) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: t('configAssistantError') || 'Sorry, I could not process your request. Please try again later.',
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

  const handleAction = (action: string, params?: Record<string, any>) => {
    if (action === 'navigate' && params) {
      if (onNavigate) {
        onNavigate(params.tab as SettingsTab, params.section);
      } else {
        router.push(`/settings?tab=${params.tab}${params.section ? `&section=${params.section}` : ''}`);
      }
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
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {message.content}
              </div>
            </div>
            {message.role === 'assistant' && message.actions && message.actions.length > 0 && (
              <div className="space-y-2">
                {message.actions.map((action, index) => (
                  <button
                    key={index}
                    onClick={() => handleAction(action.action, action.params)}
                    className="w-full text-left p-2 bg-white border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 transition-colors text-xs"
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-3 py-2 text-xs text-gray-600">
              <span className="inline-block animate-pulse">{t('thinking') || 'Thinking...'}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 pt-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={t('configAssistantPlaceholder') || 'Ask about configuration...'}
            className="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {t('send') || 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

