'use client';

import React, { useEffect, useState } from 'react';
import CapabilityExtensionSlot from './CapabilityExtensionSlot';
import CliApiKeysSection from './CliApiKeysSection';

interface RuntimeSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    workspaceId: string;
}

type ModalTab = 'channel' | 'cli-keys';

export default function RuntimeSettingsModal({
    isOpen,
    onClose,
    workspaceId,
}: RuntimeSettingsModalProps) {
    const [activeTab, setActiveTab] = useState<ModalTab>('channel');

    // Escape key handler
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isOpen) {
                onClose();
            }
        };

        if (isOpen) {
            document.body.style.overflow = 'hidden';
            document.addEventListener('keydown', handleEscape);
            return () => {
                document.body.style.overflow = '';
                document.removeEventListener('keydown', handleEscape);
            };
        } else {
            document.body.style.overflow = '';
        }
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const tabs: { id: ModalTab; label: string; icon: string }[] = [
        { id: 'channel', label: 'Mindscape Cloud Channel', icon: '🔗' },
        { id: 'cli-keys', label: 'CLI Agent Keys', icon: '🔑' },
    ];

    return (
        <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="runtime-settings-modal-title"
        >
            <div
                className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[80vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b dark:border-gray-700 flex-shrink-0">
                    <div>
                        <h2
                            id="runtime-settings-modal-title"
                            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
                        >
                            ☁️ 雲端 Runtime 設定
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                            管理 Mindscape Cloud Channel 綁定與外部服務設定
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                        aria-label="Close"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200 dark:border-gray-700 flex-shrink-0 px-5">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`
                                flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium
                                border-b-2 transition-colors -mb-px
                                ${activeTab === tab.id
                                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                                }
                            `}
                        >
                            <span>{tab.icon}</span>
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Content - Scrollable */}
                <div className="flex-1 overflow-y-auto p-5">
                    {activeTab === 'channel' && (
                        <CapabilityExtensionSlot
                            section="runtime-environments"
                            workspaceId={workspaceId}
                        />
                    )}
                    {activeTab === 'cli-keys' && (
                        <CliApiKeysSection />
                    )}
                </div>

                {/* Footer */}
                <div className="flex justify-end p-4 border-t dark:border-gray-700 flex-shrink-0">
                    <button
                        onClick={onClose}
                        className="px-5 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors text-sm"
                    >
                        關閉
                    </button>
                </div>
            </div>
        </div>
    );
}
