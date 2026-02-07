'use client';

import React, { useEffect, useState } from 'react';
import { PanelLeftClose, ChevronRight, LayoutGrid } from 'lucide-react';
import { PackPanel } from '../../app/workspaces/[workspaceId]/components/PackPanel';
import { getApiBaseUrl } from '../../lib/api-url';

interface PackListSidebarProps {
    workspaceId: string;
    isOpen: boolean;
    onClose: () => void;
}

export const PackListSidebar: React.FC<PackListSidebarProps> = ({
    workspaceId,
    isOpen,
    onClose,
}) => {
    const [mounted, setMounted] = useState(false);
    const apiUrl = getApiBaseUrl();

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) return null;

    return (
        <>
            {/* Overlay Backdrop */}
            <div
                className={`fixed inset-0 bg-black/40 backdrop-blur-sm z-50 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
                    }`}
                onClick={onClose}
            />

            {/* Sidebar Drawer */}
            <div
                className={`fixed top-0 left-0 h-full w-80 bg-white dark:bg-gray-900 shadow-2xl z-[60] transform transition-transform duration-300 ease-in-out border-r border-gray-200 dark:border-gray-800 ${isOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
            >
                <div className="flex flex-col h-full">
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 h-12 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                        <div className="flex items-center gap-2">
                            <LayoutGrid className="w-4 h-4 text-blue-500" />
                            <span className="text-sm font-bold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
                                Capabilities Pack
                            </span>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
                        >
                            <PanelLeftClose className="w-5 h-5 text-gray-500" />
                        </button>
                    </div>

                    {/* Content Wrapper */}
                    <div className="flex-1 overflow-hidden relative">
                        <PackPanel
                            workspaceId={workspaceId}
                            apiUrl={apiUrl}
                        />
                    </div>

                    {/* Footer / Quick Nav */}
                    <div className="p-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50">
                        <a
                            href={`/workspaces/${workspaceId}`}
                            className="flex items-center justify-between w-full px-3 py-2 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                        >
                            <span>前往工作區首頁</span>
                            <ChevronRight className="w-4 h-4" />
                        </a>
                    </div>
                </div>
            </div>
        </>
    );
};
