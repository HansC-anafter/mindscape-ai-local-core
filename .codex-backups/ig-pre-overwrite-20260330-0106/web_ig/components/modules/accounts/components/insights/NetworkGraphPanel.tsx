import React, { useEffect, useState } from 'react';
import { Network, Loader2, RefreshCw, Users } from 'lucide-react';

import type { NetworkOverlap, SeedInfo } from '../../insightsApi';
import { createInsightsApi } from '../../insightsApi';

interface NetworkGraphPanelProps {
    workspaceId: string;
    apiUrl: string;
    seed: string;
    allSeeds: SeedInfo[];
    onRunPlaybook?: (playbookCode: string, params: Record<string, unknown>) => void;
}

export function NetworkGraphPanel({
    workspaceId,
    apiUrl,
    seed,
    allSeeds,
    onRunPlaybook,
}: NetworkGraphPanelProps) {
    const [overlaps, setOverlaps] = useState<NetworkOverlap[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedSeeds, setSelectedSeeds] = useState<string[]>([]);
    const [minOverlap, setMinOverlap] = useState(2);

    const api = createInsightsApi(apiUrl);

    // Auto-select current seed + first other seed
    useEffect(() => {
        const others = allSeeds.filter((s) => s.seed !== seed).map((s) => s.seed);
        if (others.length > 0) {
            setSelectedSeeds([seed, others[0]]);
        } else {
            setSelectedSeeds([seed]);
        }
    }, [seed, allSeeds]);

    const loadNetwork = async () => {
        if (selectedSeeds.length < 2) return;
        setLoading(true);
        setError(null);
        try {
            const result = await api.fetchNetwork(workspaceId, selectedSeeds, minOverlap);
            setOverlaps(result);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (selectedSeeds.length >= 2) {
            loadNetwork();
        }
    }, [selectedSeeds, minOverlap]);

    const toggleSeed = (s: string) => {
        setSelectedSeeds((prev) =>
            prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
        );
    };

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-2">
                    <Network className="w-4 h-4 text-purple-500" />
                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        Network Analysis
                    </span>
                    <span className="text-xs text-gray-500">({overlaps.length} common)</span>
                </div>
                <button
                    onClick={() =>
                        onRunPlaybook?.('ig_analyze_network', {
                            seeds: selectedSeeds,
                            analysis_type: 'common_following',
                        })
                    }
                    className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-purple-500 text-white rounded-md hover:bg-purple-600 transition-colors"
                >
                    <RefreshCw className="w-3 h-3" />
                    Analyze Network
                </button>
            </div>

            {/* Seed Selector */}
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                    Compare Seeds (select 2+)
                </div>
                <div className="flex flex-wrap gap-2">
                    {allSeeds.map((s) => (
                        <button
                            key={s.seed}
                            onClick={() => toggleSeed(s.seed)}
                            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${selectedSeeds.includes(s.seed)
                                    ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 ring-1 ring-purple-300 dark:ring-purple-700'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200'
                                }`}
                        >
                            @{s.seed}
                            <span className="ml-1 opacity-60">{s.target_count}</span>
                        </button>
                    ))}
                </div>
                <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-gray-500">Min overlap:</span>
                    <select
                        value={minOverlap}
                        onChange={(e) => setMinOverlap(Number(e.target.value))}
                        className="text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded px-2 py-1"
                    >
                        <option value={2}>2+</option>
                        <option value={3}>3+</option>
                        <option value={4}>4+</option>
                        <option value={5}>5+</option>
                    </select>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {selectedSeeds.length < 2 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                        <Users className="w-8 h-8 mb-2 opacity-30" />
                        <p className="text-sm">Select at least 2 seeds to compare.</p>
                    </div>
                ) : loading ? (
                    <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
                    </div>
                ) : error ? (
                    <div className="p-4 text-sm text-red-500">{error}</div>
                ) : overlaps.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                        <Network className="w-8 h-8 mb-2 opacity-30" />
                        <p className="text-sm">No common followings found. Run network analysis first.</p>
                    </div>
                ) : (
                    <div className="p-4">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                                    <th className="pb-2 pr-4">Account</th>
                                    <th className="pb-2 pr-4">Overlap</th>
                                    <th className="pb-2">Shared By</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                {overlaps.map((o) => (
                                    <tr key={o.target_handle} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                        <td className="py-2 pr-4 font-medium text-gray-900 dark:text-gray-100">
                                            @{o.target_handle}
                                        </td>
                                        <td className="py-2 pr-4">
                                            <span className="inline-flex items-center justify-center w-6 h-6 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 rounded-full text-xs font-bold">
                                                {o.overlap_count}
                                            </span>
                                        </td>
                                        <td className="py-2">
                                            <div className="flex flex-wrap gap-1">
                                                {o.shared_by.map((s) => (
                                                    <span
                                                        key={s}
                                                        className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded text-xs"
                                                    >
                                                        @{s}
                                                    </span>
                                                ))}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
