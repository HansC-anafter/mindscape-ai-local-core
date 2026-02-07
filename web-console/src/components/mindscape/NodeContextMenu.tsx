'use client';

/**
 * NodeContextMenu - Right-click context menu for graph nodes
 */

import React from 'react';
import type { MindscapeNode } from '@/lib/mindscape-graph-api';

interface NodeContextMenuProps {
    isOpen: boolean;
    position: { x: number; y: number };
    node: MindscapeNode | null;
    onClose: () => void;
    onViewDetails: () => void;
    onContinueConversation: () => void;
    onStartNewConversation: () => void;
}

export function NodeContextMenu({
    isOpen,
    position,
    node,
    onClose,
    onViewDetails,
    onContinueConversation,
    onStartNewConversation,
}: NodeContextMenuProps) {
    if (!isOpen || !node) return null;

    const menuItems = [
        {
            icon: '📋',
            label: '查看詳情',
            onClick: onViewDetails,
        },
        { divider: true },
        {
            icon: '💬',
            label: '繼續對話',
            onClick: onContinueConversation,
            disabled: !node.metadata?.thread_id,
            disabledReason: '此節點沒有關聯的對話',
        },
        {
            icon: '🆕',
            label: '開新對話',
            onClick: onStartNewConversation,
        },
    ];

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 z-40"
                onClick={onClose}
            />

            {/* Menu */}
            <div
                className="fixed z-50 bg-white rounded-lg shadow-xl border border-gray-200 py-1 min-w-[180px] animate-in fade-in zoom-in-95 duration-100"
                style={{
                    left: position.x,
                    top: position.y,
                }}
            >
                {/* Header */}
                <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-xs text-gray-500 truncate max-w-[200px]">
                        {node.label}
                    </p>
                    <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${node.type === 'intent' ? 'bg-purple-100 text-purple-700' :
                            node.type === 'execution' ? 'bg-green-100 text-green-700' :
                                'bg-gray-100 text-gray-700'
                        }`}>
                        {node.type}
                    </span>
                </div>

                {/* Menu Items */}
                {menuItems.map((item, index) => {
                    if ('divider' in item) {
                        return <div key={index} className="my-1 border-t border-gray-100" />;
                    }

                    return (
                        <button
                            key={index}
                            onClick={() => {
                                if (!item.disabled) {
                                    item.onClick();
                                    onClose();
                                }
                            }}
                            disabled={item.disabled}
                            className={`w-full px-3 py-2 text-left text-sm flex items-center gap-2 transition-colors ${item.disabled
                                    ? 'text-gray-400 cursor-not-allowed'
                                    : 'text-gray-700 hover:bg-gray-50'
                                }`}
                            title={item.disabled ? item.disabledReason : undefined}
                        >
                            <span>{item.icon}</span>
                            <span>{item.label}</span>
                        </button>
                    );
                })}
            </div>
        </>
    );
}
