'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface LLMDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  playbookCode: string;
  systemSOP: string;
  onVariantCreated: () => void;
}

interface Suggestion {
  title: string;
  description: string;
  rationale: string;
  step_number?: number;
}

export default function LLMDrawer({
  isOpen,
  onClose,
  playbookCode,
  systemSOP,
  onVariantCreated
}: LLMDrawerProps) {
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<number>>(new Set());
  const [variantName, setVariantName] = useState('');
  const [variantDescription, setVariantDescription] = useState('');

  useEffect(() => {
    if (isOpen && messages.length === 0) {
      // Initialize with system message
      setMessages([{
        role: 'assistant',
        content: `這份 Playbook 是系統標準版，我會根據你的習慣幫你生成一份*個人版本*，原始系統版不會被修改。你可以描述：

* 你目前要用在什麼場景？
* 哪些步驟你覺得多餘或太細？
* 有沒有一定要加上的個人檢查項？`
      }]);
    }
  }, [isOpen, messages.length]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/optimize?profile_id=default-user`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ include_usage_analysis: true })
        }
      );

      if (response.ok) {
        const data = await response.json();
        const newSuggestions = data.suggestions || [];
        setSuggestions(newSuggestions);

        // Auto-select all suggestions
        setSelectedSuggestions(new Set(newSuggestions.map((_: any, i: number) => i)));

        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `根據你的需求，我為你生成了 ${newSuggestions.length} 個優化建議。請在右側預覽區查看並選擇要應用的建議。`
        }]);
      } else {
        throw new Error('Failed to get suggestions');
      }
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `抱歉，獲取優化建議時出錯：${err.message}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  const toggleSuggestion = (index: number) => {
    setSelectedSuggestions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const handleCreateVariant = async () => {
    if (!variantName.trim()) {
      alert(t('playbookEnterVariantName'));
      return;
    }

    if (selectedSuggestions.size === 0) {
      alert(t('playbookSelectAtLeastOneSuggestion'));
      return;
    }

    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const selected = Array.from(selectedSuggestions).map(i => suggestions[i]);

      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/from-suggestions?profile_id=default-user`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            variant_name: variantName,
            variant_description: variantDescription,
            selected_suggestions: selected
          })
        }
      );

      if (response.ok) {
        onVariantCreated();
        onClose();
        alert(t('playbookVariantCreated', { name: variantName }));
      } else {
        throw new Error('Failed to create variant');
      }
    } catch (err: any) {
      alert(t('playbookCreateVariantFailed', { error: err.message }));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex">
      {/* Drawer */}
      <div className="bg-surface-secondary w-full max-w-6xl ml-auto h-full flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-default">
          <h2 className="text-xl font-semibold text-gray-900">與助手討論你的使用情境</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl"
          >
            ×
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Left: Chat Area */}
          <div className="flex-1 flex flex-col border-r border-gray-200">
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-3 ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-lg p-3">
                    <p className="text-sm text-gray-600">正在分析...</p>
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-gray-200">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                  placeholder={t('describeYourUseCase')}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={loading}
                  autoComplete="off"
                  data-lpignore="true"
                  data-form-type="other"
                  data-1p-ignore="true"
                  name="llm-drawer-input"
                />
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400"
                >
                  {t('send')}
                </button>
              </div>
            </div>
          </div>

          {/* Right: Preview Area */}
          <div className="w-96 flex flex-col bg-gray-50">
            <div className="p-4 border-b border-gray-200">
              <h3 className="font-medium text-gray-900">{t('changePreview')}</h3>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {suggestions.length > 0 ? (
                <div className="space-y-3">
                  {suggestions.map((suggestion, index) => (
                    <div
                      key={index}
                      className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                        selectedSuggestions.has(index)
                          ? 'border-accent bg-accent-10 dark:border-blue-500 dark:bg-blue-900/20'
                          : 'border-default bg-surface-secondary hover:border-default'
                      }`}
                      onClick={() => toggleSuggestion(index)}
                    >
                      <div className="flex items-start gap-2">
                        <input
                          type="checkbox"
                          checked={selectedSuggestions.has(index)}
                          onChange={() => toggleSuggestion(index)}
                          className="mt-1"
                        />
                        <div className="flex-1">
                          <h4 className="font-medium text-sm text-gray-900">{suggestion.title}</h4>
                          <p className="text-xs text-gray-600 mt-1">{suggestion.description}</p>
                          {suggestion.step_number && (
                            <span className="inline-block mt-2 px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                              步驟 {suggestion.step_number}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 text-center py-8">
                  {t('afterStartingConversation')}
                </p>
              )}
            </div>

            {/* Bottom: Name and Confirm */}
            {suggestions.length > 0 && (
              <div className="p-4 border-t border-gray-200 space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    {t('variantName')}
                  </label>
                  <input
                    type="text"
                    value={variantName}
                    onChange={(e) => setVariantName(e.target.value)}
                    placeholder={t('exampleVariantName')}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                    autoComplete="off"
                    data-lpignore="true"
                    data-form-type="other"
                    data-1p-ignore="true"
                    name="variant-name-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    {t('descriptionOptional')}
                  </label>
                  <textarea
                    value={variantDescription}
                    onChange={(e) => setVariantDescription(e.target.value)}
                    placeholder={t('variantDescriptionPlaceholder')}
                    rows={2}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                    autoComplete="off"
                    data-lpignore="true"
                    data-form-type="other"
                    data-1p-ignore="true"
                    name="variant-description-input"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={onClose}
                    className="flex-1 px-3 py-2 text-sm text-gray-700 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleCreateVariant}
                    disabled={!variantName.trim() || selectedSuggestions.size === 0}
                    className="flex-1 px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
                  >
                    接受變更並建立個人版本
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
