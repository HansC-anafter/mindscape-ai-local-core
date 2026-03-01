'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import InstructionPreview from '../components/InstructionPreview';

const API_URL = getApiBaseUrl();

interface InstructionFields {
    persona: string;
    goals: string[];
    anti_goals: string[];
    style_rules: string[];
    domain_context: string;
}

const EMPTY_FIELDS: InstructionFields = {
    persona: '',
    goals: [],
    anti_goals: [],
    style_rules: [],
    domain_context: '',
};

export default function WorkspaceInstructionPage() {
    const params = useParams();
    const router = useRouter();
    const workspaceId = params?.workspaceId as string;
    const { workspace, refreshWorkspace } = useWorkspaceData();

    const [fields, setFields] = useState<InstructionFields>(EMPTY_FIELDS);
    const [savedFields, setSavedFields] = useState<InstructionFields>(EMPTY_FIELDS);
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'error'>('idle');

    // Tag input states
    const [goalInput, setGoalInput] = useState('');
    const [antiGoalInput, setAntiGoalInput] = useState('');
    const [styleInput, setStyleInput] = useState('');

    // Load instruction from workspace data
    useEffect(() => {
        if (workspace?.workspace_blueprint?.instruction) {
            const instr = workspace.workspace_blueprint.instruction;
            const loaded: InstructionFields = {
                persona: instr.persona || '',
                goals: instr.goals || [],
                anti_goals: instr.anti_goals || [],
                style_rules: instr.style_rules || [],
                domain_context: instr.domain_context || '',
            };
            setFields(loaded);
            setSavedFields(loaded);
        }
    }, [workspace]);

    const isDirty = JSON.stringify(fields) !== JSON.stringify(savedFields);

    const handleSave = useCallback(async () => {
        setSaving(true);
        setSaveStatus('idle');
        try {
            const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_blueprint: {
                        instruction: {
                            persona: fields.persona || null,
                            goals: fields.goals,
                            anti_goals: fields.anti_goals,
                            style_rules: fields.style_rules,
                            domain_context: fields.domain_context || null,
                            version: (workspace?.workspace_blueprint?.instruction?.version || 0) + 1,
                        },
                    },
                }),
            });
            if (!response.ok) throw new Error(`Save failed: ${response.status}`);
            setSavedFields({ ...fields });
            setSaveStatus('saved');
            await refreshWorkspace();
            setTimeout(() => setSaveStatus('idle'), 2000);
        } catch (err) {
            console.error('Failed to save instruction:', err);
            setSaveStatus('error');
        } finally {
            setSaving(false);
        }
    }, [fields, workspaceId, workspace, refreshWorkspace]);

    // Tag add helper
    const addTag = (field: 'goals' | 'anti_goals' | 'style_rules', value: string) => {
        const trimmed = value.trim();
        if (!trimmed) return;
        setFields(prev => ({
            ...prev,
            [field]: [...prev[field], trimmed],
        }));
    };

    const removeTag = (field: 'goals' | 'anti_goals' | 'style_rules', index: number) => {
        setFields(prev => ({
            ...prev,
            [field]: prev[field].filter((_, i) => i !== index),
        }));
    };

    const handleTagKeyDown = (
        e: React.KeyboardEvent<HTMLInputElement>,
        field: 'goals' | 'anti_goals' | 'style_rules',
        inputValue: string,
        setInputValue: (v: string) => void
    ) => {
        if (e.key === 'Enter' && inputValue.trim()) {
            e.preventDefault();
            addTag(field, inputValue);
            setInputValue('');
        }
    };

    return (
        <div className="h-full flex flex-col bg-white dark:bg-gray-950">
            {/* Top bar */}
            <div className="flex items-center justify-between px-6 py-3 border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex-shrink-0">
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => router.push(`/workspaces/${workspaceId}`)}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </button>
                    <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        Workspace Instruction
                    </h1>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                        {workspace?.title}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    {isDirty && (
                        <span className="text-xs text-amber-600 dark:text-amber-400">● 未儲存的變更</span>
                    )}
                    {saveStatus === 'saved' && (
                        <span className="text-xs text-green-600 dark:text-green-400">✓ 已儲存</span>
                    )}
                    {saveStatus === 'error' && (
                        <span className="text-xs text-red-600 dark:text-red-400">✗ 儲存失敗</span>
                    )}
                    <button
                        onClick={handleSave}
                        disabled={!isDirty || saving}
                        className="px-4 py-1.5 text-sm bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {saving ? '儲存中...' : '儲存'}
                    </button>
                </div>
            </div>

            {/* Three-column layout */}
            <div className="flex-1 overflow-hidden grid grid-cols-12 gap-0">
                {/* Left: Fields */}
                <div className="col-span-4 border-r dark:border-gray-700 overflow-y-auto">
                    <div className="p-5 space-y-5">
                        {/* Persona */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Persona
                            </label>
                            <textarea
                                value={fields.persona}
                                onChange={e => setFields(prev => ({ ...prev, persona: e.target.value }))}
                                placeholder="You are a brand strategist for a yoga studio..."
                                rows={3}
                                maxLength={500}
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none"
                            />
                            <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 text-right">
                                {fields.persona.length}/500
                            </div>
                        </div>

                        {/* Goals */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Goals
                            </label>
                            <div className="flex flex-wrap gap-1.5 mb-2">
                                {fields.goals.map((goal, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-md border border-blue-200 dark:border-blue-800">
                                        {goal}
                                        <button onClick={() => removeTag('goals', i)} className="hover:text-blue-900 dark:hover:text-blue-100">×</button>
                                    </span>
                                ))}
                            </div>
                            <input
                                value={goalInput}
                                onChange={e => setGoalInput(e.target.value)}
                                onKeyDown={e => handleTagKeyDown(e, 'goals', goalInput, setGoalInput)}
                                placeholder="輸入目標後按 Enter..."
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            />
                        </div>

                        {/* Anti-goals */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Anti-goals (DO NOT)
                            </label>
                            <div className="flex flex-wrap gap-1.5 mb-2">
                                {fields.anti_goals.map((ag, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-md border border-red-200 dark:border-red-800">
                                        {ag}
                                        <button onClick={() => removeTag('anti_goals', i)} className="hover:text-red-900 dark:hover:text-red-100">×</button>
                                    </span>
                                ))}
                            </div>
                            <input
                                value={antiGoalInput}
                                onChange={e => setAntiGoalInput(e.target.value)}
                                onKeyDown={e => handleTagKeyDown(e, 'anti_goals', antiGoalInput, setAntiGoalInput)}
                                placeholder="輸入禁止事項後按 Enter..."
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            />
                        </div>

                        {/* Style Rules */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Style Rules
                            </label>
                            <div className="flex flex-wrap gap-1.5 mb-2">
                                {fields.style_rules.map((rule, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded-md border border-purple-200 dark:border-purple-800">
                                        {rule}
                                        <button onClick={() => removeTag('style_rules', i)} className="hover:text-purple-900 dark:hover:text-purple-100">×</button>
                                    </span>
                                ))}
                            </div>
                            <input
                                value={styleInput}
                                onChange={e => setStyleInput(e.target.value)}
                                onKeyDown={e => handleTagKeyDown(e, 'style_rules', styleInput, setStyleInput)}
                                placeholder="輸入風格規則後按 Enter..."
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            />
                        </div>

                        {/* Domain Context */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Domain Context
                            </label>
                            <textarea
                                value={fields.domain_context}
                                onChange={e => setFields(prev => ({ ...prev, domain_context: e.target.value }))}
                                placeholder="背景知識、專業術語、品牌定位..."
                                rows={6}
                                maxLength={2000}
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none"
                            />
                            <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 text-right">
                                {fields.domain_context.length}/2000
                            </div>
                        </div>
                    </div>
                </div>

                {/* Middle: Preview */}
                <div className="col-span-5 border-r dark:border-gray-700 bg-white dark:bg-gray-900">
                    <InstructionPreview
                        persona={fields.persona}
                        goals={fields.goals}
                        antiGoals={fields.anti_goals}
                        styleRules={fields.style_rules}
                        domainContext={fields.domain_context}
                    />
                </div>

                {/* Right: Placeholder for LLM Chat (Phase 2) */}
                <div className="col-span-3 bg-gray-50 dark:bg-gray-900 flex flex-col">
                    <div className="flex items-center px-4 py-3 border-b dark:border-gray-700 flex-shrink-0">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">AI 指令助手</span>
                        <span className="ml-2 text-xs px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded">
                            Coming Soon
                        </span>
                    </div>
                    <div className="flex-1 flex items-center justify-center p-6">
                        <div className="text-center max-w-xs">
                            <div className="text-4xl mb-4">🤖</div>
                            <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                                AI Instruction Assistant
                            </div>
                            <div className="text-xs text-gray-400 dark:text-gray-500 mb-4">
                                即將支援：透過對話讓 AI 協助你撰寫、優化 Workspace 指令
                            </div>
                            <div className="space-y-2">
                                {[
                                    '幫我寫一個品牌顧問的 persona',
                                    '優化目前的 anti-goals',
                                    '根據我的產業補充 domain context',
                                ].map((suggestion, i) => (
                                    <div
                                        key={i}
                                        className="text-xs px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-500 dark:text-gray-400 cursor-not-allowed opacity-60"
                                    >
                                        {suggestion}
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                    <div className="p-4 border-t dark:border-gray-700 flex-shrink-0">
                        <div className="flex gap-2">
                            <input
                                type="text"
                                placeholder="Phase 2: AI-assisted editing..."
                                disabled
                                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed"
                            />
                            <button
                                disabled
                                className="px-4 py-2 text-sm bg-gray-300 dark:bg-gray-700 text-gray-500 rounded-lg cursor-not-allowed"
                            >
                                送出
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
