'use client';

import React, { useEffect } from 'react';
import WorkspaceInstructionEditor from './WorkspaceInstructionEditor';
import { t } from '@/lib/i18n';

interface WorkspaceInstructionModalProps {
    isOpen: boolean;
    onClose: () => void;
    workspaceId: string;
    apiUrl: string;
    initialInstruction?: {
        persona?: string;
        goals?: string[];
        anti_goals?: string[];
        style_rules?: string[];
        domain_context?: string;
        version?: number;
    } | null;
    onUpdate?: () => void;
}

export default function WorkspaceInstructionModal({
    isOpen,
    onClose,
    workspaceId,
    apiUrl,
    initialInstruction,
    onUpdate,
}: WorkspaceInstructionModalProps) {
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => { document.body.style.overflow = ''; };
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen) return;
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleEscape);
        return () => window.removeEventListener('keydown', handleEscape);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-5 border-b dark:border-gray-700 flex-shrink-0">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                            Workspace Instruction
                        </h2>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                            {t('workspaceInstructionDescription' as any) || 'Define AI behavior for this workspace'}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-5">
                    <WorkspaceInstructionEditor
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        initialInstruction={initialInstruction}
                        onUpdate={() => {
                            onUpdate?.();
                        }}
                    />
                </div>
            </div>
        </div>
    );
}
