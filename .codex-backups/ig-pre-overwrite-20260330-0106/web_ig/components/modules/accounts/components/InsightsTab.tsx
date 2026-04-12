import React, { useEffect, useState } from 'react';
import { Tag, FileText, Network, Brain, Loader2, ChevronDown } from 'lucide-react';

import type { SeedInfo } from '../insightsApi';
import { createInsightsApi } from '../insightsApi';
import { ProfileTagsPanel } from './insights/ProfileTagsPanel';
import { ContentAnalysisPanel } from './insights/ContentAnalysisPanel';
import { NetworkGraphPanel } from './insights/NetworkGraphPanel';
import { PersonaPanel } from './insights/PersonaPanel';

type InsightsSubTab = 'tags' | 'content' | 'network' | 'persona';

interface InsightsTabProps {
    workspaceId: string;
    apiUrl: string;
    initialSeed?: string;
    onRunPlaybook?: (playbookCode: string, params: Record<string, unknown>) => void;
}

const SUB_TABS: { key: InsightsSubTab; label: string; icon: React.FC<any>; color: string }[] = [
    { key: 'tags', label: 'Tags', icon: Tag, color: 'blue' },
    { key: 'content', label: 'Content', icon: FileText, color: 'green' },
    { key: 'network', label: 'Network', icon: Network, color: 'purple' },
    { key: 'persona', label: 'Persona', icon: Brain, color: 'amber' },
];

const COLOR_CLASSES: Record<string, { active: string; inactive: string }> = {
    blue: {
        active: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 ring-1 ring-blue-300 dark:ring-blue-700',
        inactive: 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700',
    },
    green: {
        active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 ring-1 ring-green-300 dark:ring-green-700',
        inactive: 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700',
    },
    purple: {
        active: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 ring-1 ring-purple-300 dark:ring-purple-700',
        inactive: 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700',
    },
    amber: {
        active: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 ring-1 ring-amber-300 dark:ring-amber-700',
        inactive: 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700',
    },
};

export function InsightsTab({ workspaceId, apiUrl, initialSeed, onRunPlaybook }: InsightsTabProps) {
    const [seeds, setSeeds] = useState<SeedInfo[]>([]);
    const [selectedSeed, setSelectedSeed] = useState<string>(initialSeed || '');
    const [activeSubTab, setActiveSubTab] = useState<InsightsSubTab>('tags');
    const [loading, setLoading] = useState(false);

    const api = createInsightsApi(apiUrl);

    useEffect(() => {
        const loadSeeds = async () => {
            setLoading(true);
            try {
                const result = await api.fetchSeeds(workspaceId);
                setSeeds(result);
                if (!selectedSeed && result.length > 0) {
                    setSelectedSeed(result[0].seed);
                }
            } catch (e) {
                console.error('Failed to load seeds', e);
            } finally {
                setLoading(false);
            }
        };
        loadSeeds();
    }, [workspaceId]);

    useEffect(() => {
        if (initialSeed) setSelectedSeed(initialSeed);
    }, [initialSeed]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
        );
    }

    if (seeds.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
                <Network className="w-12 h-12 mb-3 opacity-20" />
                <p className="text-sm font-medium">No seeds available</p>
                <p className="text-xs mt-1">Run a following analysis first to create seeds.</p>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Seed Selector + Sub-tabs */}
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 space-y-3">
                {/* Seed dropdown */}
                <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Seed:</span>
                    <div className="relative">
                        <select
                            value={selectedSeed}
                            onChange={(e) => setSelectedSeed(e.target.value)}
                            className="appearance-none bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 pr-8 text-sm font-medium text-gray-900 dark:text-gray-100 cursor-pointer hover:border-blue-400"
                        >
                            {seeds.map((s) => (
                                <option key={s.seed} value={s.seed}>
                                    @{s.seed} ({s.target_count} targets)
                                </option>
                            ))}
                        </select>
                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                    </div>
                </div>

                {/* Pill tabs */}
                <div className="flex items-center gap-2">
                    {SUB_TABS.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = activeSubTab === tab.key;
                        const cls = COLOR_CLASSES[tab.color];
                        return (
                            <button
                                key={tab.key}
                                onClick={() => setActiveSubTab(tab.key)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${isActive ? cls.active : cls.inactive
                                    }`}
                            >
                                <Icon className="w-3.5 h-3.5" />
                                {tab.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Sub-panel */}
            <div className="flex-1 overflow-hidden">
                {activeSubTab === 'tags' && (
                    <ProfileTagsPanel
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        seed={selectedSeed}
                        onRunPlaybook={onRunPlaybook}
                    />
                )}
                {activeSubTab === 'content' && (
                    <ContentAnalysisPanel
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        seed={selectedSeed}
                        onRunPlaybook={onRunPlaybook}
                    />
                )}
                {activeSubTab === 'network' && (
                    <NetworkGraphPanel
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        seed={selectedSeed}
                        allSeeds={seeds}
                        onRunPlaybook={onRunPlaybook}
                    />
                )}
                {activeSubTab === 'persona' && (
                    <PersonaPanel
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        seed={selectedSeed}
                        onRunPlaybook={onRunPlaybook}
                    />
                )}
            </div>
        </div>
    );
}
