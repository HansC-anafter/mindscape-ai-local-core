'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { FloatingPanel } from './FloatingPanel';
import type { MindscapeNode } from '@/lib/mindscape-graph-api';

const WorkspaceChat = dynamic(
    () => import('@/components/WorkspaceChat').then(mod => mod.default),
    {
        ssr: false,
        loading: () => (
            <div className="flex items-center justify-center h-full text-gray-400">
                Loading conversation...
            </div>
        )
    }
);

interface EmbeddedChatProps {
    isOpen: boolean;
    workspaceId: string;
    threadId?: string | null;
    node?: MindscapeNode | null;
    onClose: () => void;
    position?: { x: number; y: number };
}

export default function EmbeddedChat({
    isOpen,
    workspaceId,
    threadId,
    node,
    onClose,
    position = { x: 100, y: 100 }
}: EmbeddedChatProps) {
    if (!isOpen) return null;

    const title = threadId
        ? `Continue Conversation - ${node?.label || 'Node'}`
        : 'Start New Conversation';

    return (
        <FloatingPanel
            title={title}
            isOpen={isOpen}
            onClose={onClose}
            defaultPosition={position}
            defaultSize={{ width: 450, height: 600 }}
            minWidth={360}
            minHeight={400}
        >
            <div className="h-full flex flex-col">
                <WorkspaceChat
                    workspaceId={workspaceId}
                    threadId={threadId}
                    apiUrl={process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8300'}
                />
            </div>
        </FloatingPanel>
    );
}
