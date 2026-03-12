'use client';

import React, { useState, useEffect, useMemo } from 'react';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { getApiBaseUrl } from '../../lib/api-url';
import SkillDiscoveryChat from '../../components/skill/SkillDiscoveryChat';

const API_URL = getApiBaseUrl();

export interface SkillCard {
    id: string;
    name: string;
    description: string;
    source: 'agent' | 'capability';
    source_label: string;
    file_count: number;
    has_scripts: boolean;
    has_examples: boolean;
    has_resources: boolean;
    file_path: string;
    last_modified: string | null;
}

/* ─────────────────────────────────────────────
 * Left Sidebar — mirrors PlaybookLibrarySidebar
 * ───────────────────────────────────────────── */
function SkillSidebar({
    skills,
    selectedSource,
    onSourceChange,
    selectedSkill,
}: {
    skills: SkillCard[];
    selectedSource: string;
    onSourceChange: (s: string) => void;
    selectedSkill: SkillCard | null;
}) {
    const agentSkills = skills.filter((s) => s.source === 'agent');
    const capSkills = skills.filter((s) => s.source === 'capability');

    // Group capability skills by source pack (use id prefix or source_label)
    const capByPack = useMemo(() => {
        const map: Record<string, SkillCard[]> = {};
        capSkills.forEach((s) => {
            const pack = s.id;
            if (!map[pack]) map[pack] = [];
            map[pack].push(s);
        });
        return map;
    }, [capSkills]);

    const filterItem = (key: string, label: string, count: number) => (
        <button
            key={key}
            onClick={() => onSourceChange(key)}
            className={`w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors ${selectedSource === key
                ? 'bg-gray-200/70 dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-medium'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
        >
            {label} ({count})
        </button>
    );

    return (
        <div className="bg-surface-secondary dark:bg-gray-900 h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-0 border-r border-default dark:border-gray-800 overflow-y-auto">
            {/* Section: 篩選標籤 */}
            <h3 className="text-sm font-bold text-primary dark:text-gray-100 mb-3">篩選分類</h3>

            {/* My filters */}
            <div className="mb-4">
                <h4 className="text-xs font-semibold text-secondary dark:text-gray-400 mb-2">依來源</h4>
                <div className="space-y-0.5">
                    {filterItem('all', '全部技能', skills.length)}
                    {filterItem('agent', '🤖 Agent Skills', agentSkills.length)}
                    {filterItem('capability', '📦 Capability Packs', capSkills.length)}
                </div>
            </div>

            {/* Pack list — mirrors 依 Packs section */}
            {capSkills.length > 0 && (
                <div className="mb-4">
                    <h4 className="text-xs font-semibold text-secondary dark:text-gray-400 mb-2">依 Packs</h4>
                    <div className="space-y-0.5">
                        {Object.entries(capByPack)
                            .sort(([, a], [, b]) => b.length - a.length)
                            .map(([pack, items]) => (
                                <button
                                    key={pack}
                                    onClick={() => onSourceChange(`pack:${pack}`)}
                                    className={`w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors ${selectedSource === `pack:${pack}`
                                        ? 'bg-gray-200/70 dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-medium'
                                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                                        }`}
                                >
                                    {pack} ({items.length})
                                </button>
                            ))}
                    </div>
                </div>
            )}

            {/* Agent skills list */}
            {agentSkills.length > 0 && (
                <div className="mb-4">
                    <h4 className="text-xs font-semibold text-secondary dark:text-gray-400 mb-2">Agent Skills</h4>
                    <div className="space-y-0.5">
                        {agentSkills.map((s) => (
                            <button
                                key={s.id}
                                onClick={() => onSourceChange(`skill:${s.id}`)}
                                className={`w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors truncate ${selectedSource === `skill:${s.id}`
                                    ? 'bg-gray-200/70 dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-medium'
                                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                                    }`}
                            >
                                {s.name}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

/* ─────────────────────────────────────────────
 * Main Page
 * ───────────────────────────────────────────── */
export default function SkillsPage() {
    const [skills, setSkills] = useState<SkillCard[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedSource, setSelectedSource] = useState('all');
    const [selectedSkill, setSelectedSkill] = useState<SkillCard | null>(null);

    useEffect(() => {
        loadSkills();
    }, []);

    const loadSkills = async () => {
        try {
            setLoading(true);
            setError(null);
            const apiUrl = API_URL.startsWith('http') ? API_URL : '';
            const response = await fetch(`${apiUrl}/api/v1/skills/`);
            if (!response.ok) {
                throw new Error(`Failed to load skills: ${response.statusText}`);
            }
            const data = await response.json();
            setSkills(data);
        } catch (err: any) {
            console.error('Failed to load skills:', err);
            setError(err.message || 'Failed to load skills');
        } finally {
            setLoading(false);
        }
    };

    const filteredSkills = useMemo(() => {
        return skills.filter((skill) => {
            // Search filter
            const matchesSearch =
                !searchTerm ||
                skill.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                skill.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                skill.id.toLowerCase().includes(searchTerm.toLowerCase());

            // Source filter
            let matchesSource = true;
            if (selectedSource === 'agent') {
                matchesSource = skill.source === 'agent';
            } else if (selectedSource === 'capability') {
                matchesSource = skill.source === 'capability';
            } else if (selectedSource.startsWith('pack:')) {
                matchesSource = skill.id === selectedSource.replace('pack:', '');
            } else if (selectedSource.startsWith('skill:')) {
                matchesSource = skill.id === selectedSource.replace('skill:', '');
            }

            return matchesSearch && matchesSource;
        });
    }, [skills, searchTerm, selectedSource]);

    return (
        <div className="min-h-screen bg-surface dark:bg-gray-950">
            <Header />

            {/* Page Header — matches playbooks header */}
            <div className="bg-surface-secondary dark:bg-gray-900 border-b border-default dark:border-gray-800">
                <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
                    <div className="flex flex-wrap items-center gap-3">
                        <h1 className="text-xl font-bold text-primary dark:text-gray-100 whitespace-nowrap flex-shrink-0">
                            Skills 技能庫
                        </h1>

                        {/* Spacer */}
                        <div className="flex-1" />

                        {/* Search */}
                        <input
                            type="text"
                            placeholder="搜尋 Skill..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-36 lg:w-48 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
                        />

                        {/* Reload */}
                        <button
                            onClick={loadSkills}
                            disabled={loading}
                            className="px-3 py-1.5 text-sm bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                        >
                            {loading ? '載入中...' : '重新載入'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Three Column Layout — matches playbooks grid-cols-12 */}
            <main className="w-full">
                <div className="grid grid-cols-12 gap-0">

                    {/* Left Column: Sidebar (col-span-2) */}
                    <div className="col-span-12 lg:col-span-2">
                        <SkillSidebar
                            skills={skills}
                            selectedSource={selectedSource}
                            onSourceChange={setSelectedSource}
                            selectedSkill={selectedSkill}
                        />
                    </div>

                    {/* Middle Column: Skill Cards (col-span-7) */}
                    <div className="col-span-12 lg:col-span-7">
                        <div className="h-[calc(100vh-8rem)] flex flex-col">
                            {error && (
                                <div className="m-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
                                    {error}
                                </div>
                            )}

                            {loading ? (
                                <div className="p-4">
                                    <p className="text-secondary dark:text-gray-400">載入中...</p>
                                </div>
                            ) : filteredSkills.length === 0 ? (
                                <div className="p-4">
                                    <div className="bg-surface-accent dark:bg-gray-800 shadow rounded-lg p-12 text-center">
                                        <p className="text-secondary dark:text-gray-400">
                                            {searchTerm ? `找不到匹配「${searchTerm}」的技能` : '尚未安裝任何技能'}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex-1 overflow-y-auto p-4">
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                        {filteredSkills.map((skill) => {
                                            const isSelected = selectedSkill?.id === skill.id && selectedSkill?.source === skill.source;
                                            const modifiedDate = skill.last_modified
                                                ? new Date(skill.last_modified).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric', year: 'numeric' })
                                                : null;

                                            return (
                                                <div
                                                    key={`${skill.source}-${skill.id}`}
                                                    onClick={() => setSelectedSkill(skill)}
                                                    className={`bg-surface-secondary dark:bg-gray-800 rounded-lg shadow p-6 hover:shadow-lg transition-shadow flex flex-col cursor-pointer border ${isSelected
                                                        ? 'border-accent dark:border-blue-500 ring-1 ring-accent/30'
                                                        : 'border-default dark:border-gray-700'
                                                        }`}
                                                >
                                                    {/* Top row: Icon + badges */}
                                                    <div className="flex items-center gap-2 flex-wrap mb-3">
                                                        <span className="text-3xl">{skill.source === 'agent' ? '🤖' : '📦'}</span>
                                                        <span className={`text-xs px-2 py-1 rounded ${skill.source === 'agent'
                                                            ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                                                            : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                                                            }`}>
                                                            {skill.source_label}
                                                        </span>
                                                        {skill.has_scripts && (
                                                            <span className="text-xs px-2 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded">scripts</span>
                                                        )}
                                                    </div>

                                                    {/* Title */}
                                                    <h3 className="text-base font-bold text-primary dark:text-gray-100 mb-2">
                                                        {skill.name}
                                                    </h3>

                                                    {/* Description */}
                                                    <p className="text-sm text-secondary dark:text-gray-400 mb-4 flex-1 line-clamp-3">
                                                        {skill.description || 'No description available'}
                                                    </p>

                                                    {/* Tags */}
                                                    <div className="flex items-center gap-2 flex-wrap mb-3">
                                                        <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-tertiary dark:text-gray-400 rounded">
                                                            {skill.file_count} 個檔案
                                                        </span>
                                                        {skill.has_examples && (
                                                            <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-tertiary dark:text-gray-400 rounded">examples</span>
                                                        )}
                                                        {skill.has_resources && (
                                                            <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-tertiary dark:text-gray-400 rounded">resources</span>
                                                        )}
                                                    </div>

                                                    {/* Bottom row: ID + date */}
                                                    <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-100 dark:border-gray-700">
                                                        <span className="text-xs text-tertiary dark:text-gray-500 font-mono">{skill.id}</span>
                                                        {modifiedDate && (
                                                            <span className="text-xs text-tertiary dark:text-gray-500">{modifiedDate}</span>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Column: Skill Discovery Chat (col-span-3) */}
                    <div className="col-span-12 lg:col-span-4 xl:col-span-3">
                        <div className="bg-surface-primary dark:bg-gray-900 shadow h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-0 border-l border-default dark:border-gray-800">
                            <SkillDiscoveryChat selectedSkill={selectedSkill} />
                        </div>
                    </div>

                </div>
            </main>
        </div>
    );
}
