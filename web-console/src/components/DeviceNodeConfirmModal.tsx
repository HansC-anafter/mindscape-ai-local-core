'use client';

import React, { useEffect, useState } from 'react';
import { BaseModal } from './BaseModal';

interface ConfirmationRequest {
    nonce: string;
    tool_call_id: string;
    tool: string;
    arguments: Record<string, unknown>;
    arguments_hash: string;
    trust_level: string;
    preview?: string;
    expires_at: number;
}

interface DeviceNodeConfirmModalProps {
    apiBaseUrl?: string;
    pollingInterval?: number;
}

const TRUST_LEVEL_CONFIG: Record<string, { color: string; icon: string; label: string }> = {
    read: { color: 'text-green-600', icon: '👁️', label: '讀取' },
    draft: { color: 'text-yellow-600', icon: '📝', label: '草稿' },
    execute: { color: 'text-orange-600', icon: '⚡', label: '執行' },
    admin: { color: 'text-red-600', icon: '🔐', label: '管理員' },
};

export function DeviceNodeConfirmModal({
    apiBaseUrl = '',
    pollingInterval = 1000
}: DeviceNodeConfirmModalProps) {
    const [confirmations, setConfirmations] = useState<ConfirmationRequest[]>([]);
    const [connected, setConnected] = useState(false);
    const [responding, setResponding] = useState<string | null>(null);

    useEffect(() => {
        const fetchConfirmations = async () => {
            try {
                const response = await fetch(`${apiBaseUrl}/device-node/confirmations`);
                const data = await response.json();
                setConfirmations(data.confirmations || []);
                setConnected(data.connected || false);
            } catch (error) {
                console.error('Failed to fetch confirmations:', error);
            }
        };

        fetchConfirmations();
        const interval = setInterval(fetchConfirmations, pollingInterval);
        return () => clearInterval(interval);
    }, [apiBaseUrl, pollingInterval]);

    const handleRespond = async (confirmation: ConfirmationRequest, approved: boolean) => {
        setResponding(confirmation.nonce);
        try {
            await fetch(`${apiBaseUrl}/device-node/confirmations/${confirmation.nonce}/respond`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_call_id: confirmation.tool_call_id,
                    arguments_hash: confirmation.arguments_hash,
                    approved,
                }),
            });
            setConfirmations(prev => prev.filter(c => c.nonce !== confirmation.nonce));
        } catch (error) {
            console.error('Failed to respond:', error);
        } finally {
            setResponding(null);
        }
    };

    const getTimeRemaining = (expiresAt: number) => {
        const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
        return `${remaining}s`;
    };

    const currentConfirmation = confirmations[0];
    if (!currentConfirmation) return null;

    const trustConfig = TRUST_LEVEL_CONFIG[currentConfirmation.trust_level.toLowerCase()] || TRUST_LEVEL_CONFIG.execute;

    return (
        <BaseModal
            isOpen={!!currentConfirmation}
            onClose={() => handleRespond(currentConfirmation, false)}
            title="Device Node 操作確認"
            maxWidth="max-w-lg"
        >
            <div className="space-y-4">
                {/* Device Status */}
                <div className="flex items-center justify-between text-sm">
                    <span className="text-secondary">Device Node</span>
                    <span className={connected ? 'text-green-600' : 'text-red-600'}>
                        {connected ? '● 已連線' : '○ 未連線'}
                    </span>
                </div>

                {/* Trust Level Badge */}
                <div className="flex items-center gap-2">
                    <span className={`text-2xl`}>{trustConfig.icon}</span>
                    <span className={`font-medium ${trustConfig.color}`}>
                        {trustConfig.label}權限
                    </span>
                    <span className="ml-auto text-sm text-secondary">
                        ⏱️ {getTimeRemaining(currentConfirmation.expires_at)}
                    </span>
                </div>

                {/* Tool Info */}
                <div className="bg-surface-secondary dark:bg-gray-700 rounded-lg p-4">
                    <div className="font-mono text-sm font-medium text-primary">
                        {currentConfirmation.tool}
                    </div>
                    {currentConfirmation.preview && (
                        <div className="mt-2 text-sm text-secondary">
                            {currentConfirmation.preview}
                        </div>
                    )}
                </div>

                {/* Arguments */}
                <details className="group">
                    <summary className="cursor-pointer text-sm text-secondary hover:text-primary">
                        查看參數詳情
                    </summary>
                    <pre className="mt-2 text-xs bg-gray-100 dark:bg-gray-800 p-3 rounded overflow-x-auto">
                        {JSON.stringify(currentConfirmation.arguments, null, 2)}
                    </pre>
                </details>

                {/* Hash for verification */}
                <div className="text-xs text-tertiary font-mono truncate">
                    hash: {currentConfirmation.arguments_hash.slice(0, 16)}...
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3 pt-2">
                    <button
                        onClick={() => handleRespond(currentConfirmation, false)}
                        disabled={responding === currentConfirmation.nonce}
                        className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                       text-secondary hover:bg-surface-secondary transition-colors
                       disabled:opacity-50"
                    >
                        拒絕
                    </button>
                    <button
                        onClick={() => handleRespond(currentConfirmation, true)}
                        disabled={responding === currentConfirmation.nonce}
                        className="flex-1 px-4 py-2 bg-brand-primary text-white rounded-lg
                       hover:bg-brand-primary/90 transition-colors
                       disabled:opacity-50"
                    >
                        {responding === currentConfirmation.nonce ? '處理中...' : '允許'}
                    </button>
                </div>

                {/* Pending count */}
                {confirmations.length > 1 && (
                    <div className="text-center text-sm text-secondary">
                        還有 {confirmations.length - 1} 個待確認
                    </div>
                )}
            </div>
        </BaseModal>
    );
}
