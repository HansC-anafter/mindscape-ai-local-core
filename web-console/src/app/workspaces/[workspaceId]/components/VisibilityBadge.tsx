'use client';

import React, { useState, useRef, useEffect } from 'react';
import type { WorkspaceVisibility } from '../workspace-page.types';

interface VisibilityBadgeProps {
    workspaceId: string;
    visibility: WorkspaceVisibility;
    apiUrl: string;
    onVisibilityChange?: (newVisibility: WorkspaceVisibility) => void;
}

const VISIBILITY_CONFIG: Record<WorkspaceVisibility, {
    icon: string;
    label: string;
    colorClass: string;
    bgClass: string;
    description: string;
}> = {
    private: {
        icon: '🔒',
        label: 'Private',
        colorClass: 'text-gray-600 dark:text-gray-400',
        bgClass: 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700',
        description: 'Only you can access',
    },
    group: {
        icon: '👥',
        label: 'Group',
        colorClass: 'text-blue-600 dark:text-blue-400',
        bgClass: 'bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50',
        description: 'Shared with group members',
    },
    discoverable: {
        icon: '🔍',
        label: 'Discoverable',
        colorClass: 'text-amber-600 dark:text-amber-400',
        bgClass: 'bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/40',
        description: 'Others can find this workspace',
    },
    public: {
        icon: '🌐',
        label: 'Public',
        colorClass: 'text-green-600 dark:text-green-400',
        bgClass: 'bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/40',
        description: 'Anyone can access',
    },
};

// Options available in the dropdown (group is auto-set, not user-selectable)
const SELECTABLE_OPTIONS: WorkspaceVisibility[] = ['private', 'discoverable', 'public'];

export default function VisibilityBadge({
    workspaceId,
    visibility,
    apiUrl,
    onVisibilityChange,
}: VisibilityBadgeProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [currentVisibility, setCurrentVisibility] = useState(visibility);
    const [isUpdating, setIsUpdating] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        setCurrentVisibility(visibility);
    }, [visibility]);

    // Close dropdown on outside click
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
            return () => document.removeEventListener('mousedown', handleClickOutside);
        }
    }, [isOpen]);

    const config = VISIBILITY_CONFIG[currentVisibility] || VISIBILITY_CONFIG.private;

    const handleSelect = async (newVisibility: WorkspaceVisibility) => {
        if (newVisibility === currentVisibility) {
            setIsOpen(false);
            return;
        }

        setIsUpdating(true);
        try {
            const res = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visibility: newVisibility }),
            });
            if (res.ok) {
                setCurrentVisibility(newVisibility);
                onVisibilityChange?.(newVisibility);
            } else {
                console.error('[VisibilityBadge] Failed to update visibility:', res.status);
            }
        } catch (err) {
            console.error('[VisibilityBadge] Error updating visibility:', err);
        } finally {
            setIsUpdating(false);
            setIsOpen(false);
        }
    };

    return (
        <div ref={dropdownRef} className="relative inline-flex">
            {/* Badge button */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                disabled={isUpdating}
                className={`
                    flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium
                    transition-colors cursor-pointer select-none
                    ${config.bgClass} ${config.colorClass}
                    ${isUpdating ? 'opacity-50 cursor-wait' : ''}
                `}
                title={config.description}
            >
                <span>{config.icon}</span>
                <span>{config.label}</span>
                <svg className="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d={isOpen ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'} />
                </svg>
            </button>

            {/* Dropdown */}
            {isOpen && (
                <div className="absolute top-full left-0 mt-1 w-48 rounded-lg shadow-lg border
                    bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700
                    py-1 z-50 animate-in fade-in slide-in-from-top-1 duration-150"
                >
                    {SELECTABLE_OPTIONS.map((opt) => {
                        const optConfig = VISIBILITY_CONFIG[opt];
                        const isActive = opt === currentVisibility;
                        return (
                            <button
                                key={opt}
                                onClick={() => handleSelect(opt)}
                                className={`
                                    w-full text-left px-3 py-2 flex items-center gap-2 text-sm
                                    transition-colors
                                    ${isActive
                                        ? 'bg-gray-100 dark:bg-gray-800'
                                        : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                                    }
                                `}
                            >
                                <span className="text-base">{optConfig.icon}</span>
                                <div className="flex-1 min-w-0">
                                    <div className={`font-medium ${optConfig.colorClass}`}>
                                        {optConfig.label}
                                    </div>
                                    <div className="text-xs text-gray-500 dark:text-gray-500">
                                        {optConfig.description}
                                    </div>
                                </div>
                                {isActive && (
                                    <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none"
                                        stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round"
                                            strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                )}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
