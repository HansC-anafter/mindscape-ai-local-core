'use client';

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { t } from '../../lib/i18n';

import { getApiBaseUrl } from '../../lib/api-url';
import type { SkillCard } from '../../app/skills/page';

const API_URL = getApiBaseUrl();

interface AgentStepInfo {
    step_number: number;
    thought: string;
    action?: string;
    action_result?: string;
    success?: boolean;
}

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    steps?: AgentStepInfo[];
    error?: string;
}

interface SkillDiscoveryChatProps {
    selectedSkill: SkillCard | null;
}

export default function SkillDiscoveryChat({
    selectedSkill,
}: SkillDiscoveryChatProps) {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: 'initial',
            role: 'assistant',
            content: t('Welcome! I am the Mindscape Skill Assistant. You can ask me to help you package and install capability packs (skills). For example: "Please package and install the ig skill."' as any),
            timestamp: new Date()
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const suggestedQuestions = useMemo(() => {
        const baseQuestions = [
            t('How do I install a skill?' as any),
            t('What agent skills are available?' as any),
        ];

        if (selectedSkill) {
            if (selectedSkill.source === 'capability') {
                baseQuestions.unshift(t(`Package and install ${selectedSkill.name}` as any));
            } else {
                baseQuestions.unshift(t(`Tell me more about ${selectedSkill.name}` as any));
            }
        }

        return baseQuestions.slice(0, 3);
    }, [selectedSkill]);

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

            const systemPrompt = `You are the Mindscape AI Skill Assistant.
You help users explore, package, and install capabilities and agent skills.
If the user asks to install a capability pack, you MUST use the install_skill tool to package and install it.
Do NOT output thinking process in the final response if the tool is executing properly, just summarize the result concisely.
User currently has selected: ${selectedSkill ? selectedSkill.name : 'None'}.`;

            const response = await fetch(`${apiUrl}/api/v1/system-settings/assistant/agent-chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: userMessage.content,
                    max_iterations: 5,
                    system_prompt: systemPrompt
                })
            });

            if (response.ok) {
                const data = await response.json();

                let content = data.final_answer || '';

                if (data.status === 'failed') {
                    content = `Failed to process request: ${data.error || 'Unknown error'}`;
                }

                const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: content,
                    timestamp: new Date(),
                    steps: data.steps || [],
                    error: data.error
                };
                setMessages(prev => [...prev, assistantMessage]);
            } else {
                throw new Error('Failed to get response');
            }
        } catch (err) {
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: t('Sorry, I could not process your request. Please try again later.' as any),
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
        <div className="flex flex-col h-full bg-surface-primary dark:bg-gray-900 rounded-lg shadow border border-default p-4">
            <div className="mb-4 pb-2 border-b border-default">
                <h2 className="text-sm font-semibold text-primary">{t('Skill Assistant' as any)}</h2>
                <p className="text-xs text-secondary mt-1">{t('Ask me to install or configure skills' as any)}</p>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 mb-4">
                {messages.map((message) => (
                    <div key={message.id} className="space-y-2">
                        <div
                            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap ${message.role === 'user'
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200'
                                    }`}
                            >
                                {message.content}
                            </div>
                        </div>
                        {message.role === 'assistant' && message.steps && message.steps.length > 0 && (
                            <div className="ml-2 space-y-1">
                                {message.steps.map((step: any, idx: number) => (
                                    <div key={idx} className="text-[10px] text-gray-500 bg-gray-50 dark:bg-gray-800/50 p-1.5 rounded border border-gray-100 dark:border-gray-700/50">
                                        <div className="font-semibold">{step.action ? `Action: ${step.action}` : 'Thinking...'}</div>
                                        {step.action_result && <div className="mt-1 font-mono text-gray-400 line-clamp-2 truncate">{step.action_result}</div>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
                {isLoading && (
                    <div className="flex justify-start">
                        <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
                            <span className="inline-block animate-pulse">{t('Thinking...' as any)}</span>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
                {suggestedQuestions.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-3">
                        {suggestedQuestions.map((question, idx) => (
                            <button
                                key={idx}
                                onClick={async () => {
                                    if (isLoading) return;
                                    setInput(question);
                                }}
                                disabled={isLoading}
                                className="px-3 py-1.5 text-[11px] bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-full hover:bg-accent-10 dark:hover:bg-blue-900/20 hover:border-accent dark:hover:border-blue-600 transition-colors text-primary dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
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
                        placeholder={t('Type a message...' as any)}
                        className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                        disabled={isLoading}
                    />
                    <button
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading}
                        className="px-4 py-2 text-sm bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                    >
                        {t('Send' as any)}
                    </button>
                </div>
            </div>
        </div>
    );
}
