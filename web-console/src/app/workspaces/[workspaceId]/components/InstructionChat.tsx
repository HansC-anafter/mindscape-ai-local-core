'use client';

import React, { useMemo, useRef, useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

interface InstructionFields {
    persona: string;
    goals: string[];
    anti_goals: string[];
    style_rules: string[];
    domain_context: string;
}

interface InstructionPatch {
    persona?: string | null;
    goals?: string[] | null;
    anti_goals?: string[] | null;
    style_rules?: string[] | null;
    domain_context?: string | null;
}

interface InstructionChatResponse {
    assistant_message: string;
    patch: InstructionPatch;
    changed_fields: string[];
    confidence?: number | null;
}

interface InstructionChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    patch?: InstructionPatch;
    changedFields?: string[];
    applied?: boolean;
    isError?: boolean;
}

interface InstructionChatProps {
    workspaceId: string;
    apiUrl: string;
    currentInstruction: InstructionFields;
    onApplyPatch: (patch: InstructionPatch) => void;
}

function hasPatch(patch?: InstructionPatch): boolean {
    return !!patch && Object.keys(patch).length > 0;
}

function fieldLabel(field: string): string {
    const map: Record<string, string> = {
        persona: 'persona',
        goals: 'goals',
        anti_goals: 'anti-goals',
        style_rules: 'style-rules',
        domain_context: 'domain-context',
    };
    return map[field] || field;
}

export default function InstructionChat({
    workspaceId,
    apiUrl,
    currentInstruction,
    onApplyPatch,
}: InstructionChatProps) {
    const [messages, setMessages] = useState<InstructionChatMessage[]>([
        {
            id: 'initial',
            role: 'assistant',
            content: t('instructionChatInitialMessage' as any),
        },
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const suggestedPrompts = useMemo(
        () => [
            '幫我把 persona 改成 B2B SaaS 成長顧問',
            '補上 3 條 anti-goals，避免空泛回答',
            '讓 style rules 偏向簡短、條列、可執行',
        ],
        []
    );

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const applyPatchForMessage = (messageId: string) => {
        const target = messages.find(msg => msg.id === messageId);
        if (!target || !hasPatch(target.patch) || target.applied) return;

        onApplyPatch(target.patch!);
        setMessages(prev =>
            prev.map(msg =>
                msg.id === messageId
                    ? { ...msg, applied: true }
                    : msg
            )
        );
    };

    const sendMessage = async (content: string) => {
        const trimmed = content.trim();
        if (!trimmed || isLoading) return;

        const userMessage: InstructionChatMessage = {
            id: `u-${Date.now()}`,
            role: 'user',
            content: trimmed,
        };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const history = messages.slice(-8).map(msg => ({
                role: msg.role,
                content: msg.content,
            }));

            const response = await fetch(
                `${apiUrl}/api/v1/workspaces/${workspaceId}/instruction/chat`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: trimmed,
                        history,
                        current_instruction: currentInstruction,
                    }),
                }
            );

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }

            const data: InstructionChatResponse = await response.json();
            const assistantMessage: InstructionChatMessage = {
                id: `a-${Date.now()}`,
                role: 'assistant',
                content: data.assistant_message || '已生成建議，可直接套用。',
                patch: data.patch || {},
                changedFields: data.changed_fields || [],
            };
            setMessages(prev => [...prev, assistantMessage]);
        } catch (err: any) {
            const errorMessage: InstructionChatMessage = {
                id: `e-${Date.now()}`,
                role: 'assistant',
                content: `${t('instructionChatErrorPrefix' as any)}${err?.message || 'Unknown error'}`,
                isError: true,
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
            <div className="flex items-center justify-between px-4 py-3 border-b dark:border-gray-700 flex-shrink-0">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('instructionChatTitle' as any)}
                </span>
                <span className="text-xs px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded">
                    {t('instructionChatPhaseTag' as any)}
                </span>
            </div>

            <div className="px-4 py-3 border-b dark:border-gray-700 flex-shrink-0">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('instructionChatQuickPrompts' as any)}</div>
                <div className="space-y-1.5">
                    {suggestedPrompts.map(prompt => (
                        <button
                            key={prompt}
                            onClick={() => sendMessage(prompt)}
                            disabled={isLoading}
                            className="w-full text-left text-xs px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md hover:border-blue-400 dark:hover:border-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {prompt}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {messages.map(msg => (
                    <div key={msg.id} className="space-y-2">
                        <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div
                                className={`max-w-[92%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap ${msg.role === 'user'
                                    ? 'bg-blue-600 text-white'
                                    : msg.isError
                                        ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
                                        : 'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700'
                                    }`}
                            >
                                {msg.content}
                            </div>
                        </div>

                        {msg.role === 'assistant' && hasPatch(msg.patch) && (
                            <div className="ml-1 space-y-2">
                                <div className="flex flex-wrap gap-1.5">
                                    {(msg.changedFields || Object.keys(msg.patch || {})).map(field => (
                                        <span
                                            key={field}
                                            className="text-[10px] px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300"
                                        >
                                            {fieldLabel(field)}
                                        </span>
                                    ))}
                                </div>
                                <button
                                    onClick={() => applyPatchForMessage(msg.id)}
                                    disabled={msg.applied}
                                    className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                                >
                                    {msg.applied ? t('instructionChatApplied' as any) : t('instructionChatApply' as any)}
                                </button>
                            </div>
                        )}
                    </div>
                ))}
                {isLoading && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">{t('instructionChatThinking' as any)}</div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t dark:border-gray-700 flex-shrink-0">
                <div className="flex gap-2">
                    <input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                sendMessage(input);
                            }
                        }}
                        placeholder={t('instructionChatInputPlaceholder' as any)}
                        disabled={isLoading}
                        className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
                    />
                    <button
                        onClick={() => sendMessage(input)}
                        disabled={!input.trim() || isLoading}
                        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                    >
                        {t('instructionChatSend' as any)}
                    </button>
                </div>
            </div>
        </div>
    );
}
