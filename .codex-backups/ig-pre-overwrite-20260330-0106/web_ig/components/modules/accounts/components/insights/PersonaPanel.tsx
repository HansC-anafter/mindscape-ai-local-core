import React, { useEffect, useState } from 'react';
import { Brain, Loader2, RefreshCw, Star } from 'lucide-react';

import type { Persona } from '../../insightsApi';
import { createInsightsApi } from '../../insightsApi';

interface PersonaPanelProps {
    workspaceId: string;
    apiUrl: string;
    seed?: string;
    handle?: string;
    onRunPlaybook?: (playbookCode: string, params: Record<string, unknown>) => void;
}

function ScoreBar({ value, label }: { value: number | null; label: string }) {
    const pct = value != null ? Math.round(value * 100) : 0;
    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-28 shrink-0">{label}</span>
            <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                    className="h-full bg-gradient-to-r from-amber-400 to-amber-600 rounded-full transition-all"
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span className="text-xs text-gray-600 dark:text-gray-400 w-10 text-right">{pct}%</span>
        </div>
    );
}

export function PersonaPanel({ workspaceId, apiUrl, seed, handle, onRunPlaybook }: PersonaPanelProps) {
    const [personas, setPersonas] = useState<Persona[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const api = createInsightsApi(apiUrl);

    const loadPersonas = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await api.fetchPersonas(workspaceId, {
                seed: seed || undefined,
                handles: handle ? [handle] : undefined,
            });
            setPersonas(result);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPersonas();
    }, [seed, handle]);

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-2">
                    <Brain className="w-4 h-4 text-amber-500" />
                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        AI Personas
                    </span>
                    <span className="text-xs text-gray-500">({personas.length} generated)</span>
                </div>
                <button
                    onClick={() => onRunPlaybook?.('ig_generate_personas', { seed: seed || handle, locale: 'zh-TW' })}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-amber-500 text-white rounded-md hover:bg-amber-600 transition-colors"
                >
                    <RefreshCw className="w-3 h-3" />
                    Generate Personas
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {loading ? (
                    <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-amber-500" />
                    </div>
                ) : error ? (
                    <div className="p-4 text-sm text-red-500">{error}</div>
                ) : personas.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                        <Brain className="w-8 h-8 mb-2 opacity-30" />
                        <p className="text-sm">No personas generated yet. Run persona generation first.</p>
                    </div>
                ) : (
                    <div className="p-4 space-y-4">
                        {personas.map((persona) => {
                            let traits: string[] = [];
                            let themes: string[] = [];
                            let demographics: Record<string, any> = {};

                            try { traits = persona.key_traits_json ? JSON.parse(persona.key_traits_json) : []; } catch { /* */ }
                            try { themes = persona.content_themes_json ? JSON.parse(persona.content_themes_json) : []; } catch { /* */ }
                            try { demographics = persona.estimated_demographics_json ? JSON.parse(persona.estimated_demographics_json) : {}; } catch { /* */ }

                            return (
                                <div
                                    key={persona.id || persona.account_handle}
                                    className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
                                >
                                    {/* Persona Header */}
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center gap-2">
                                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-bold">
                                                {persona.account_handle.charAt(0).toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                                    @{persona.account_handle}
                                                </div>
                                                {demographics.likely_location && (
                                                    <div className="text-xs text-gray-500">
                                                        📍 {demographics.likely_location}
                                                        {demographics.age_range && ` · ${demographics.age_range}`}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        {persona.collaboration_potential != null && (
                                            <div className="flex items-center gap-1">
                                                <Star className="w-4 h-4 text-amber-500" />
                                                <span className="text-sm font-bold text-amber-600 dark:text-amber-400">
                                                    {Math.round(persona.collaboration_potential * 100)}%
                                                </span>
                                            </div>
                                        )}
                                    </div>

                                    {/* Summary */}
                                    {persona.persona_summary && (
                                        <p className="text-sm text-gray-700 dark:text-gray-300 mb-3 leading-relaxed">
                                            {persona.persona_summary}
                                        </p>
                                    )}

                                    {/* Traits */}
                                    {traits.length > 0 && (
                                        <div className="flex flex-wrap gap-1.5 mb-3">
                                            {traits.map((trait, i) => (
                                                <span
                                                    key={i}
                                                    className="px-2 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 rounded-full text-xs"
                                                >
                                                    {trait}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Themes */}
                                    {themes.length > 0 && (
                                        <div className="flex flex-wrap gap-1.5 mb-3">
                                            {themes.map((theme, i) => (
                                                <span
                                                    key={i}
                                                    className="px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-full text-xs"
                                                >
                                                    {theme}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Collaboration Score */}
                                    <ScoreBar value={persona.collaboration_potential} label="Collaboration" />

                                    {/* Recommended Approach */}
                                    {persona.recommended_approach && (
                                        <div className="mt-3 p-2 bg-gray-50 dark:bg-gray-900/30 rounded text-xs text-gray-600 dark:text-gray-400 italic">
                                            💡 {persona.recommended_approach}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
