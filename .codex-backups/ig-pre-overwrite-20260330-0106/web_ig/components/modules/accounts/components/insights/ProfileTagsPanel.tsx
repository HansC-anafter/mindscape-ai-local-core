import React, { useEffect, useState } from 'react';
import { Tag, Filter, RefreshCw, Loader2 } from 'lucide-react';

import type { ProfileTag } from '../../insightsApi';
import { createInsightsApi } from '../../insightsApi';

interface ProfileTagsPanelProps {
    workspaceId: string;
    apiUrl: string;
    seed?: string;
    handle?: string;
    onRunPlaybook?: (playbookCode: string, params: Record<string, unknown>) => void;
}

const TIER_COLORS: Record<string, string> = {
    mega: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    macro: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    mid: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    micro: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    nano: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
};

const TYPE_COLORS: Record<string, string> = {
    kol: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    brand: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    personal: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    media: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    unknown: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

export function ProfileTagsPanel({ workspaceId, apiUrl, seed, handle, onRunPlaybook }: ProfileTagsPanelProps) {
    const [tags, setTags] = useState<ProfileTag[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [filterType, setFilterType] = useState<string>('');
    const [filterTier, setFilterTier] = useState<string>('');

    const api = createInsightsApi(apiUrl);

    const loadTags = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await api.fetchProfileTags(workspaceId, seed, {
                account_type: filterType || undefined,
                influence_tier: filterTier || undefined,
                handle: handle || undefined,
            });
            setTags(result);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadTags();
    }, [seed, handle, filterType, filterTier]);

    // Tier distribution
    const tierCounts: Record<string, number> = {};
    tags.forEach((t) => {
        const tier = t.influence_tier || 'unknown';
        tierCounts[tier] = (tierCounts[tier] || 0) + 1;
    });
    const maxTierCount = Math.max(...Object.values(tierCounts), 1);

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-2">
                    <Tag className="w-4 h-4 text-blue-500" />
                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        Profile Tags
                    </span>
                    <span className="text-xs text-gray-500">({tags.length} accounts)</span>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => onRunPlaybook?.('ig_tag_profiles', { seed: seed || handle })}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
                    >
                        <RefreshCw className="w-3 h-3" />
                        Run Tagging
                    </button>
                </div>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-4 px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-2">
                    <Filter className="w-3 h-3 text-gray-400" />
                    <select
                        value={filterType}
                        onChange={(e) => setFilterType(e.target.value)}
                        className="text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded px-2 py-1"
                    >
                        <option value="">All Types</option>
                        <option value="kol">KOL</option>
                        <option value="brand">Brand</option>
                        <option value="personal">Personal</option>
                        <option value="media">Media</option>
                    </select>
                    <select
                        value={filterTier}
                        onChange={(e) => setFilterTier(e.target.value)}
                        className="text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded px-2 py-1"
                    >
                        <option value="">All Tiers</option>
                        <option value="mega">Mega (1M+)</option>
                        <option value="macro">Macro (100K-1M)</option>
                        <option value="mid">Mid (10K-100K)</option>
                        <option value="micro">Micro (1K-10K)</option>
                        <option value="nano">Nano (&lt;1K)</option>
                    </select>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {loading ? (
                    <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                    </div>
                ) : error ? (
                    <div className="p-4 text-sm text-red-500">{error}</div>
                ) : tags.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                        <Tag className="w-8 h-8 mb-2 opacity-30" />
                        <p className="text-sm">No tags yet. Run tagging to analyze accounts.</p>
                    </div>
                ) : (
                    <div className="p-4 space-y-4">
                        {/* Tier Distribution */}
                        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                            <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Influence Tier Distribution</div>
                            <div className="space-y-1.5">
                                {['mega', 'macro', 'mid', 'micro', 'nano'].map((tier) => (
                                    <div key={tier} className="flex items-center gap-2">
                                        <span className="text-xs w-12 text-gray-500 capitalize">{tier}</span>
                                        <div className="flex-1 h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div
                                                className={`h-full rounded-full ${TIER_COLORS[tier]?.split(' ')[0] || 'bg-gray-400'}`}
                                                style={{ width: `${((tierCounts[tier] || 0) / maxTierCount) * 100}%` }}
                                            />
                                        </div>
                                        <span className="text-xs w-6 text-right text-gray-500">{tierCounts[tier] || 0}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Table */}
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                                        <th className="pb-2 pr-4">Handle</th>
                                        <th className="pb-2 pr-4">Type</th>
                                        <th className="pb-2 pr-4">Tier</th>
                                        <th className="pb-2 pr-4">Engagement</th>
                                        <th className="pb-2">Keywords</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                    {tags.map((tag) => {
                                        let keywords: string[] = [];
                                        try {
                                            keywords = tag.bio_keywords_json ? JSON.parse(tag.bio_keywords_json) : [];
                                        } catch { /* ignore */ }

                                        return (
                                            <tr key={tag.id || tag.account_handle} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                                <td className="py-2 pr-4 font-medium text-gray-900 dark:text-gray-100">
                                                    @{tag.account_handle}
                                                </td>
                                                <td className="py-2 pr-4">
                                                    <span className={`px-2 py-0.5 rounded-full text-xs ${TYPE_COLORS[tag.account_type || 'unknown']}`}>
                                                        {tag.account_type || '—'}
                                                    </span>
                                                </td>
                                                <td className="py-2 pr-4">
                                                    <span className={`px-2 py-0.5 rounded-full text-xs ${TIER_COLORS[tag.influence_tier || ''] || 'bg-gray-100 text-gray-500'}`}>
                                                        {tag.influence_tier || '—'}
                                                    </span>
                                                </td>
                                                <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">
                                                    {tag.engagement_potential != null
                                                        ? (tag.engagement_potential * 100).toFixed(0) + '%'
                                                        : '—'}
                                                </td>
                                                <td className="py-2">
                                                    <div className="flex flex-wrap gap-1">
                                                        {keywords.slice(0, 4).map((kw, i) => (
                                                            <span key={i} className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded text-xs">
                                                                {kw}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
