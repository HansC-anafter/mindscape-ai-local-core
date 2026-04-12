/**
 * Tab header component for switching between logs, actions, and ready tabs
 */
import React from 'react';
import { History, Sparkles, Activity } from 'lucide-react';
import type { TabType } from '../types';

interface TabHeaderProps {
    activeTab: TabType;
    setActiveTab: (tab: TabType) => void;
}

export function TabHeader({ activeTab, setActiveTab }: TabHeaderProps) {
    return (
        <div className="flex items-center justify-between gap-1">
            <button
                onClick={() => setActiveTab('logs')}
                className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-md text-xs transition-colors ${activeTab === 'logs'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
            >
                <History className="w-3.5 h-3.5" />
                {activeTab === 'logs' && <span className="text-[11px] font-semibold uppercase tracking-wide">Logs</span>}
            </button>
            <button
                onClick={() => setActiveTab('actions')}
                className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-md text-xs transition-colors ${activeTab === 'actions'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
            >
                <Sparkles className="w-3.5 h-3.5" />
                {activeTab === 'actions' && <span className="text-[11px] font-semibold uppercase tracking-wide">Actions</span>}
            </button>
            <button
                onClick={() => setActiveTab('ready')}
                className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-md text-xs transition-colors ${activeTab === 'ready'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
            >
                <Activity className="w-3.5 h-3.5" />
                {activeTab === 'ready' && <span className="text-[11px] font-semibold uppercase tracking-wide">Ready</span>}
            </button>
        </div>
    );
}
