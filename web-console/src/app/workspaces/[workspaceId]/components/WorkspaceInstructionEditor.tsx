'use client';

import React, { useState, useEffect, useCallback } from 'react';

interface WorkspaceInstruction {
    persona?: string;
    goals?: string[];
    anti_goals?: string[];
    style_rules?: string[];
    domain_context?: string;
    version?: number;
}

interface WorkspaceInstructionEditorProps {
    workspaceId: string;
    apiUrl: string;
    initialInstruction?: WorkspaceInstruction | null;
    onUpdate?: () => void;
}

export default function WorkspaceInstructionEditor({
    workspaceId,
    apiUrl,
    initialInstruction,
    onUpdate,
}: WorkspaceInstructionEditorProps) {
    const [persona, setPersona] = useState('');
    const [goals, setGoals] = useState<string[]>([]);
    const [antiGoals, setAntiGoals] = useState<string[]>([]);
    const [styleRules, setStyleRules] = useState<string[]>([]);
    const [domainContext, setDomainContext] = useState('');

    // Track originals for dirty detection
    const [originalData, setOriginalData] = useState('');
    const [isDirty, setIsDirty] = useState(false);

    // Input fields for adding list items
    const [goalInput, setGoalInput] = useState('');
    const [antiGoalInput, setAntiGoalInput] = useState('');
    const [styleInput, setStyleInput] = useState('');

    // UI state
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const serializeState = useCallback(() => {
        return JSON.stringify({ persona, goals, antiGoals, styleRules, domainContext });
    }, [persona, goals, antiGoals, styleRules, domainContext]);

    useEffect(() => {
        if (initialInstruction) {
            setPersona(initialInstruction.persona || '');
            setGoals(initialInstruction.goals || []);
            setAntiGoals(initialInstruction.anti_goals || []);
            setStyleRules(initialInstruction.style_rules || []);
            setDomainContext(initialInstruction.domain_context || '');
        }
    }, [initialInstruction]);

    // Set original data after loading
    useEffect(() => {
        if (initialInstruction !== undefined) {
            const p = initialInstruction?.persona || '';
            const g = initialInstruction?.goals || [];
            const ag = initialInstruction?.anti_goals || [];
            const sr = initialInstruction?.style_rules || [];
            const dc = initialInstruction?.domain_context || '';
            setOriginalData(JSON.stringify({ persona: p, goals: g, antiGoals: ag, styleRules: sr, domainContext: dc }));
        }
    }, [initialInstruction]);

    useEffect(() => {
        if (originalData) {
            setIsDirty(serializeState() !== originalData);
        }
    }, [serializeState, originalData]);

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        setSuccess(false);

        try {
            const instruction: WorkspaceInstruction = {
                persona: persona.trim() || undefined,
                goals: goals.length > 0 ? goals : undefined,
                anti_goals: antiGoals.length > 0 ? antiGoals : undefined,
                style_rules: styleRules.length > 0 ? styleRules : undefined,
                domain_context: domainContext.trim() || undefined,
            };

            const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_blueprint: { instruction },
                }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: 'Failed to save' }));
                throw new Error(errData.detail || 'Failed to save instruction');
            }

            setOriginalData(serializeState());
            setIsDirty(false);
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
            onUpdate?.();
        } catch (err: any) {
            setError(err.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    const addToList = (value: string, list: string[], setter: (v: string[]) => void, inputSetter: (v: string) => void) => {
        const trimmed = value.trim();
        if (trimmed && !list.includes(trimmed)) {
            setter([...list, trimmed]);
            inputSetter('');
        }
    };

    const removeFromList = (index: number, list: string[], setter: (v: string[]) => void) => {
        setter(list.filter((_, i) => i !== index));
    };

    const handleKeyDown = (
        e: React.KeyboardEvent, value: string, list: string[], setter: (v: string[]) => void, inputSetter: (v: string) => void
    ) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addToList(value, list, setter, inputSetter);
        }
    };

    return (
        <div className="space-y-4">
            <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    Workspace Instruction
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                    Define how the AI should behave in this workspace. These instructions are injected into every LLM call.
                </p>
            </div>

            {/* Persona */}
            <div>
                <label htmlFor="ws-persona" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Persona
                </label>
                <input
                    id="ws-persona"
                    type="text"
                    value={persona}
                    onChange={(e) => setPersona(e.target.value)}
                    maxLength={500}
                    placeholder="e.g. You are an IG content strategist"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <p className="mt-1 text-xs text-gray-400">{persona.length}/500</p>
            </div>

            {/* Goals */}
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Goals
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                    {goals.map((g, i) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700">
                            {g}
                            <button onClick={() => removeFromList(i, goals, setGoals)} className="text-emerald-500 hover:text-emerald-700 ml-0.5" aria-label="Remove">&times;</button>
                        </span>
                    ))}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={goalInput}
                        onChange={(e) => setGoalInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, goalInput, goals, setGoals, setGoalInput)}
                        placeholder="Add goal, press Enter"
                        className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                        onClick={() => addToList(goalInput, goals, setGoals, setGoalInput)}
                        className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-md hover:bg-emerald-700 transition-colors"
                    >
                        +
                    </button>
                </div>
            </div>

            {/* Anti-Goals */}
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Anti-Goals (DO NOT)
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                    {antiGoals.map((g, i) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700">
                            {g}
                            <button onClick={() => removeFromList(i, antiGoals, setAntiGoals)} className="text-red-500 hover:text-red-700 ml-0.5" aria-label="Remove">&times;</button>
                        </span>
                    ))}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={antiGoalInput}
                        onChange={(e) => setAntiGoalInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, antiGoalInput, antiGoals, setAntiGoals, setAntiGoalInput)}
                        placeholder="Add anti-goal, press Enter"
                        className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                        onClick={() => addToList(antiGoalInput, antiGoals, setAntiGoals, setAntiGoalInput)}
                        className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                    >
                        +
                    </button>
                </div>
            </div>

            {/* Style Rules */}
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Style Rules
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                    {styleRules.map((s, i) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 border border-violet-300 dark:border-violet-700">
                            {s}
                            <button onClick={() => removeFromList(i, styleRules, setStyleRules)} className="text-violet-500 hover:text-violet-700 ml-0.5" aria-label="Remove">&times;</button>
                        </span>
                    ))}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={styleInput}
                        onChange={(e) => setStyleInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, styleInput, styleRules, setStyleRules, setStyleInput)}
                        placeholder="e.g. Always reply in zh-TW"
                        className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                        onClick={() => addToList(styleInput, styleRules, setStyleRules, setStyleInput)}
                        className="px-3 py-1.5 text-sm bg-violet-600 text-white rounded-md hover:bg-violet-700 transition-colors"
                    >
                        +
                    </button>
                </div>
            </div>

            {/* Domain Context */}
            <div>
                <label htmlFor="ws-domain-context" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Domain Context
                </label>
                <textarea
                    id="ws-domain-context"
                    value={domainContext}
                    onChange={(e) => setDomainContext(e.target.value)}
                    maxLength={2000}
                    rows={3}
                    placeholder="Background context about this workspace's domain..."
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-y"
                />
                <p className="mt-1 text-xs text-gray-400">{domainContext.length}/2000</p>
            </div>

            {/* Status Messages */}
            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-2">
                    <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
                </div>
            )}
            {success && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
                    <p className="text-xs text-green-700 dark:text-green-300">Instruction saved</p>
                </div>
            )}

            {/* Save Button */}
            <div className="flex justify-end">
                <button
                    onClick={handleSave}
                    disabled={saving || !isDirty}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                    {saving ? 'Saving...' : 'Save Instruction'}
                </button>
            </div>
        </div>
    );
}
