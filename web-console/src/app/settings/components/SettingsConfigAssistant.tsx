'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '../../../lib/i18n';
import { useSettingsContext, type SettingsContext } from '../hooks/useSettingsContext';
import type { SettingsTab } from '../types';

import { getApiBaseUrl } from '../../../lib/api-url';

const API_URL = getApiBaseUrl();

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const adjustTextareaHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '0px';
      const scrollHeight = textareaRef.current.scrollHeight;
      const maxHeight = 120;
      const minHeight = 40;
      const newHeight = Math.max(minHeight, Math.min(scrollHeight, maxHeight));
      textareaRef.current.style.height = `${newHeight}px`;
    }
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [input, adjustTextareaHeight]);

  useEffect(() => {
    if (textareaRef.current) {
      adjustTextareaHeight();
    }
  }, [adjustTextareaHeight]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const generateWelcomeMessage = useCallback((ctx: SettingsContext | null, tab: SettingsTab): { content: string; actions?: Array<{ label: string; action: string; params?: Record<string, any> }> } => {
    const issues: string[] = [];
    const actions: Array<{ label: string; action: string; params?: Record<string, any> }> = [];
    let content = '';
    let suggestions: string[] = [];
    const currentTab = ctx?.currentTab || tab;

    if (!ctx) {
      switch (tab) {
        case 'basic':
          content = t('configAssistantBasicTab') || 'You are on the Basic Settings page.';
          suggestions.push(t('configAssistantBasicSuggestion1') || 'Configure LLM API keys (OpenAI or Anthropic)');
          suggestions.push(t('configAssistantBasicSuggestion2') || 'Set backend mode (local or remote)');
          break;
        case 'tools':
          content = t('configAssistantToolsTab') || 'You are on the Tools & Integrations page.';
          suggestions.push(t('configAssistantToolsSuggestion1') || 'Connect external tools (WordPress, Google Drive, etc.)');
          suggestions.push(t('configAssistantToolsSuggestion2') || 'Manage tool connections and permissions');
          break;
        case 'packs':
          content = t('configAssistantPacksTab') || 'You are on the Capability Packs page.';
          suggestions.push(t('configAssistantPacksSuggestion1') || 'Install capability suites (AI members + Playbooks)');
          suggestions.push(t('configAssistantPacksSuggestion2') || 'Install individual capability packages');
          suggestions.push(t('configAssistantPacksSuggestion3') || 'Install from .mindpack file');
          break;
        case 'service_status':
          content = t('configAssistantServiceStatusTab') || 'You are on the Service Status page.';
          suggestions.push(t('configAssistantServiceStatusSuggestion1') || 'Check system health and service status');
          suggestions.push(t('configAssistantServiceStatusSuggestion2') || 'View service issues and recommendations');
          break;
        default:
          content = t('configAssistantWelcome') || 'Welcome! I can help you with:';
          suggestions.push(t('configAssistantHelpLLM') || 'Configure LLM API keys');
          suggestions.push(t('configAssistantHelpTools') || 'Connect tools and services');
          suggestions.push(t('configAssistantHelpDiagnose') || 'Diagnose configuration issues');
          suggestions.push(t('configAssistantHelpAnswer') || 'Answer configuration questions');
      }

      if (suggestions.length > 0) {
        content += '\n\n' + (t('configAssistantSuggestions') || 'Suggestions:');
        suggestions.forEach((suggestion, index) => {
          content += `\n${index + 1}. ${suggestion}`;
        });
      }

      return { content, actions: actions.length > 0 ? actions : undefined };
    }

    const { configSnapshot } = ctx;

    switch (currentTab) {
      case 'basic':
        content = t('configAssistantBasicTab') || 'You are on the Basic Settings page.';
        suggestions.push(t('configAssistantBasicSuggestion1') || 'Configure LLM API keys (OpenAI or Anthropic)');
        suggestions.push(t('configAssistantBasicSuggestion2') || 'Set backend mode (local or remote)');
        if (!configSnapshot.backend.openai_configured && !configSnapshot.backend.anthropic_configured) {
          issues.push(t('configAssistantIssueNoLLM') || 'No LLM API keys configured');
          actions.push({
            label: t('configureLLMKeys') || 'Configure LLM Keys',
            action: 'navigate',
            params: { tab: 'basic' }
          });
        }
        break;

      case 'tools':
        if (currentSection === 'third-party-workflow') {
          content = '您正在設定第三方工作流程整合頁面。';
          suggestions.push('這些整合可以讓 AI 自動處理重複任務');
          suggestions.push('通常需要技術夥伴協助設定外部服務');
          suggestions.push('如果只有本機環境，可以先略過這些設定');
        } else if (currentSection === 'developer-integrations') {
          content = '您正在設定開發者整合頁面。';
          suggestions.push('這些工具需要外部環境或技術協作');
          suggestions.push('適合有工程師或服務商協助的團隊');
          suggestions.push('一般使用者可以先略過');
        } else if (currentSection === 'general-integrations') {
          content = '您正在設定一般整合頁面。';
          suggestions.push('這些是常用的工具整合');
          suggestions.push('在本地核心模式下即可正常使用');
          suggestions.push('建議從這些開始設定');
        } else if (currentSection === 'system-tools') {
          content = '您正在設定系統工具頁面。';
          suggestions.push('這些是系統級的本地工具');
          suggestions.push('包含向量資料庫、本地檔案系統等');
          suggestions.push('建議優先設定這些基礎工具');
        } else {
        content = t('configAssistantToolsTab') || 'You are on the Tools & Integrations page.';
        suggestions.push(t('configAssistantToolsSuggestion1') || 'Connect external tools (WordPress, Google Drive, etc.)');
        suggestions.push(t('configAssistantToolsSuggestion2') || 'Manage tool connections and permissions');
        }

        if (configSnapshot.tools.issues.length > 0) {
          issues.push(`${configSnapshot.tools.issues.length} ${t('configAssistantIssueTools') || 'tools not connected'}`);
          actions.push({
            label: t('connectTools') || 'Connect Tools',
            action: 'navigate',
            params: { tab: 'tools' }
          });
        }
        break;

      case 'packs':
        content = t('configAssistantPacksTab') || 'You are on the Capability Packs page.';
        suggestions.push(t('configAssistantPacksSuggestion1') || 'Install capability suites (AI members + Playbooks)');
        suggestions.push(t('configAssistantPacksSuggestion2') || 'Install individual capability packages');
        suggestions.push(t('configAssistantPacksSuggestion3') || 'Install from .mindpack file');
        if (configSnapshot.packs.installed === 0) {
          suggestions.push(t('configAssistantPacksSuggestion4') || 'Start by installing a capability suite');
        }
        break;

      case 'service_status':
        content = t('configAssistantServiceStatusTab') || 'You are on the Service Status page.';
        suggestions.push(t('configAssistantServiceStatusSuggestion1') || 'Check system health and service status');
        suggestions.push(t('configAssistantServiceStatusSuggestion2') || 'View service issues and recommendations');
        if (configSnapshot.services.issues.length > 0) {
          issues.push(`${configSnapshot.services.issues.length} ${t('configAssistantIssueServices') || 'service issues'}`);
        }
        break;

      default:
        content = t('configAssistantWelcome') || 'Welcome! I can help you with:';
        suggestions.push(t('configAssistantHelpLLM') || 'Configure LLM API keys');
        suggestions.push(t('configAssistantHelpTools') || 'Connect tools and services');
        suggestions.push(t('configAssistantHelpDiagnose') || 'Diagnose configuration issues');
        suggestions.push(t('configAssistantHelpAnswer') || 'Answer configuration questions');
    }

    if (suggestions.length > 0) {
      content += '\n\n' + (t('configAssistantSuggestions') || 'Suggestions:');
      suggestions.forEach((suggestion, index) => {
        content += `\n${index + 1}. ${suggestion}`;
      });
    }

    if (issues.length > 0) {
      content += `\n\n${t('configAssistantDetectedIssues') || '⚠️ Detected issues'}: ${issues.join(', ')}`;
    }

    if (actions.length === 0 && currentTab !== 'packs') {
      actions.push({
        label: t('viewAllSettings') || 'View All Settings',
        action: 'navigate',
        params: { tab: 'basic' }
      });
    }

    return { content, actions: actions.length > 0 ? actions : undefined };
  }, []);

  useEffect(() => {
    const welcome = generateWelcomeMessage(context, currentTab);
    const welcomeMessageId = 'welcome';

    setMessages(prev => {
      const existingWelcome = prev.find(m => m.id === welcomeMessageId);
      if (existingWelcome && existingWelcome.content === welcome.content) {
        return prev;
      }

      const otherMessages = prev.filter(m => m.id !== welcomeMessageId);
      return [{
        id: welcomeMessageId,
        role: 'assistant' as const,
        content: welcome.content,
        timestamp: new Date(),
        actions: welcome.actions
      }, ...otherMessages];
    });
  }, [context, currentTab, generateWelcomeMessage]);

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

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
                    ? 'bg-blue-600 dark:bg-blue-700 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
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
                    className="w-full text-left p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-300 dark:hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-xs text-gray-900 dark:text-gray-100"
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
            <div className="bg-gray-100 dark:bg-gray-700 rounded-lg px-3 py-2 text-xs text-gray-600 dark:text-gray-300">
              <span className="inline-block animate-pulse">{t('thinking') || 'Thinking...'}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 pt-3 flex-shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
            }}
            onKeyDown={handleKeyPress}
            onInput={adjustTextareaHeight}
            placeholder={t('configAssistantPlaceholder') || 'Ask about configuration...'}
            className="flex-1 px-3 py-2 text-xs border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 resize-none overflow-y-auto min-h-[2.5rem] max-h-[120px] leading-5"
            disabled={isLoading}
            rows={1}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 text-xs bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed h-[2.5rem] flex-shrink-0"
          >
            {t('send') || 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

