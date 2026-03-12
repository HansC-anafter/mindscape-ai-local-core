'use client';

import { useState, lazy, Suspense } from 'react';
import { DashboardView } from './DashboardView';
import { LocalContentView } from './LocalContentView';

// Lazy-load the Chat Capture Workbench (capability component)
// No apiUrl needed — uses same-origin, Next.js rewrites proxy /api/* to backend
const ChatCaptureWorkbench = lazy(
    () => import('@/app/capabilities/chat_capture/components/ChatCaptureWorkbench')
);


type SidebarView = 'dashboard' | 'local-content' | 'chat-capture';

interface SidebarItem {
    id: SidebarView;
    icon: string;
    label: string;
}

const SIDEBAR_ITEMS: SidebarItem[] = [
    { id: 'dashboard', icon: '📊', label: '儀表板' },
    { id: 'local-content', icon: '📁', label: '本機內容' },
    { id: 'chat-capture', icon: '📡', label: '外部對話' },
];

export function WorkspaceLayout() {
    const [activeView, setActiveView] = useState<SidebarView>('dashboard');

    return (
        <div className="flex h-screen bg-white dark:bg-gray-900">
            {/* Icon Sidebar */}
            <div className="w-14 bg-gray-950 flex flex-col items-center py-4 gap-1 border-r border-gray-800">
                {SIDEBAR_ITEMS.map((item) => {
                    const isActive = activeView === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => setActiveView(item.id)}
                            title={item.label}
                            className={`
                w-10 h-10 rounded-xl flex items-center justify-center text-lg
                transition-all duration-200 relative group
                ${isActive
                                    ? 'bg-blue-600/20 ring-1 ring-blue-500/40 shadow-lg shadow-blue-500/10'
                                    : 'hover:bg-gray-800/60'
                                }
              `}
                        >
                            <span className={`transition-transform duration-150 ${isActive ? 'scale-110' : 'group-hover:scale-105'}`}>
                                {item.icon}
                            </span>

                            {/* Active indicator bar */}
                            {isActive && (
                                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-blue-500 rounded-r-full" />
                            )}

                            {/* Tooltip */}
                            <div className="absolute left-full ml-2 px-2 py-1 bg-gray-800 text-white text-xs rounded-md opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap transition-opacity z-50">
                                {item.label}
                            </div>
                        </button>
                    );
                })}
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0">
                {activeView === 'dashboard' && <DashboardView />}
                {activeView === 'local-content' && <LocalContentView />}
                {activeView === 'chat-capture' && (
                    <Suspense fallback={
                        <div className="flex items-center justify-center h-full text-gray-400">
                            Loading Chat Capture…
                        </div>
                    }>
                        <ChatCaptureWorkbench />
                    </Suspense>
                )}
            </div>
        </div>
    );
}
