'use client';

/**
 * Mindscape Canvas Page
 *
 * Canvas page with floating panels for node details and context menu.
 * Uses React Flow (MIT licensed).
 */

import React, { useState, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import Header from '@/components/Header';
import type { MindscapeNode } from '@/lib/mindscape-graph-api';
import { NodeDetailPanel } from '@/components/mindscape/NodeDetailPanel';
import { NodeContextMenu } from '@/components/mindscape/NodeContextMenu';
import EmbeddedChat from '@/components/mindscape/EmbeddedChat';

// Dynamic import of MindscapeCanvas to avoid SSR issues
const MindscapeCanvas = dynamic(
    () => import('@/components/mindscape/MindscapeCanvas'),
    {
        ssr: false,
        loading: () => (
            <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
                <span className="text-gray-400">Loading canvas...</span>
            </div>
        ),
    }
);

export default function MindscapeCanvasPage() {
    const searchParams = useSearchParams();
    const workspaceId = searchParams?.get('workspaceId') || searchParams?.get('workspace_id');

    // State for selected node (floating panel)
    const [selectedNode, setSelectedNode] = useState<MindscapeNode | null>(null);

    // State for context menu
    const [contextMenu, setContextMenu] = useState<{
        isOpen: boolean;
        position: { x: number; y: number };
        node: MindscapeNode | null;
    }>({
        isOpen: false,
        position: { x: 0, y: 0 },
        node: null,
    });

    // State for embedded chat panel
    const [chatPanel, setChatPanel] = useState<{
        isOpen: boolean;
        threadId: string | null;
        node: MindscapeNode | null;
    }>({
        isOpen: false,
        threadId: null,
        node: null,
    });

    // Handle node click - show floating detail panel
    const handleNodeSelect = useCallback((node: MindscapeNode | null) => {
        console.log('[MindscapeCanvasPage] Node selected:', node?.id);
        setSelectedNode(node);
        // Close context menu if open
        setContextMenu(prev => ({ ...prev, isOpen: false }));
    }, []);

    // Handle node right-click - show context menu
    const handleNodeContextMenu = useCallback((event: React.MouseEvent, node: MindscapeNode) => {
        console.log('[MindscapeCanvasPage] Node context menu:', node.id);
        setContextMenu({
            isOpen: true,
            position: { x: event.clientX, y: event.clientY },
            node,
        });
    }, []);

    // Context menu actions
    const handleViewDetails = useCallback(() => {
        if (contextMenu.node) {
            setSelectedNode(contextMenu.node);
        }
    }, [contextMenu.node]);

    const handleContinueConversation = useCallback(() => {
        const node = contextMenu.node || selectedNode;
        if (node?.metadata?.thread_id) {
            console.log('[MindscapeCanvasPage] Continue conversation, thread_id:', node.metadata.thread_id);
            setChatPanel({
                isOpen: true,
                threadId: node.metadata.thread_id,
                node,
            });
            closeContextMenu();
        } else {
            console.log('[MindscapeCanvasPage] No thread_id found, starting new conversation');
            handleStartNewConversation();
        }
    }, [contextMenu.node, selectedNode]);

    const handleStartNewConversation = useCallback(() => {
        const node = contextMenu.node || selectedNode;
        console.log('[MindscapeCanvasPage] Start new conversation from node:', node?.id);
        setChatPanel({
            isOpen: true,
            threadId: null, // New conversation
            node,
        });
        closeContextMenu();
    }, [contextMenu.node, selectedNode]);

    const closeChatPanel = useCallback(() => {
        setChatPanel(prev => ({ ...prev, isOpen: false }));
    }, []);

    const closeContextMenu = useCallback(() => {
        setContextMenu(prev => ({ ...prev, isOpen: false }));
    }, []);

    // No workspaceId = show error
    if (!workspaceId) {
        return (
            <div className="min-h-screen bg-gray-50">
                <Header />
                <div className="max-w-7xl mx-auto px-4 py-6">
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
                        <h2 className="text-lg font-semibold text-yellow-800 mb-2">⚠️ 缺少 Workspace ID</h2>
                        <p className="text-yellow-700">
                            請從 Workspace 頁面進入心智執行圖，或在 URL 中加入 ?workspaceId=xxx
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50">
            <Header />

            <div className="max-w-7xl mx-auto px-4 py-6">
                {/* Page Header */}
                <div className="mb-6">
                    <h1 className="text-2xl font-bold text-gray-900 mb-2">
                        🧠 心智執行圖
                    </h1>
                    <p className="text-gray-600">
                        Workspace: <span className="font-mono text-sm">{workspaceId}</span>
                    </p>
                    <p className="text-sm text-gray-500 mt-1">
                        💡 點擊節點查看詳情 | 右鍵開啟選單
                    </p>
                </div>

                {/* Main Canvas */}
                <div className="bg-white rounded-xl shadow-lg overflow-hidden">
                    <div className="h-[600px]">
                        <MindscapeCanvas
                            workspaceId={workspaceId}
                            onNodeSelect={handleNodeSelect}
                            onNodeContextMenu={handleNodeContextMenu}
                        />
                    </div>
                </div>
            </div>

            {/* Floating Node Detail Panel */}
            {selectedNode && (
                <NodeDetailPanel
                    node={selectedNode}
                    onClose={() => setSelectedNode(null)}
                    onContinueConversation={handleContinueConversation}
                    onStartNewConversation={handleStartNewConversation}
                />
            )}

            {/* Right-click Context Menu */}
            <NodeContextMenu
                isOpen={contextMenu.isOpen}
                position={contextMenu.position}
                node={contextMenu.node}
                onClose={closeContextMenu}
                onViewDetails={handleViewDetails}
                onContinueConversation={handleContinueConversation}
                onStartNewConversation={handleStartNewConversation}
            />

            {/* Embedded Chat Panel */}
            <EmbeddedChat
                isOpen={chatPanel.isOpen}
                workspaceId={workspaceId}
                threadId={chatPanel.threadId}
                node={chatPanel.node}
                onClose={closeChatPanel}
                position={{ x: 500, y: 100 }}
            />
        </div>
    );
}
