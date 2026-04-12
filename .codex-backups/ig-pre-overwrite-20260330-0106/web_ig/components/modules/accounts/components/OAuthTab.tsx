import React from 'react';
import { AlertCircle, CheckCircle2, ExternalLink, RefreshCw, Settings, Shield } from 'lucide-react';
import type { ConnectedAccount } from '../types';

export function OAuthTab(props: {
    workspaceId: string;
    apiUrl: string;
    connectedAccounts: ConnectedAccount[];
    onRefreshAccounts: () => void;
}) {
    const { connectedAccounts, onRefreshAccounts } = props;
    const hasConnected = connectedAccounts.length > 0;

    return (
        <div className="flex-1 overflow-y-auto space-y-4 p-1">
            {/* Connected Instagram Channels */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                            Instagram Channel Bindings
                        </h3>
                    </div>
                    <button
                        onClick={onRefreshAccounts}
                        className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>

                {!hasConnected ? (
                    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                        <div className="flex items-start gap-3">
                            <Settings className="w-5 h-5 text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
                            <div>
                                <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100 mb-1">
                                    No Instagram channels bound to this workspace
                                </p>
                                <p className="text-xs text-yellow-700 dark:text-yellow-300 mb-3">
                                    To connect Instagram via Site-Hub OAuth:
                                </p>
                                <ol className="text-xs text-yellow-700 dark:text-yellow-300 list-decimal list-inside space-y-1 mb-3">
                                    <li>Open <strong>Workspace Settings → Runtime Settings</strong></li>
                                    <li>Ensure Google OAuth is connected (green indicator)</li>
                                    <li>Click <strong>「綁定 Channel」</strong> and select your Instagram channel</li>
                                </ol>
                                <p className="text-xs text-gray-400 dark:text-gray-500 italic">
                                    If you haven't created an IG channel yet, go to Site-Hub Console → Create Channel → Instagram first.
                                </p>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-2">
                        {connectedAccounts.map((account) => (
                            <div
                                key={account.channel_config_id}
                                className="p-3 bg-gray-50 dark:bg-gray-900/30 rounded-lg border border-gray-200 dark:border-gray-700"
                            >
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                            {account.channel_name}
                                        </div>
                                        {account.username && (
                                            <div className="text-xs text-gray-500 dark:text-gray-400">
                                                @{account.username}
                                            </div>
                                        )}
                                    </div>
                                    <span
                                        className={`px-2 py-0.5 text-xs rounded-full font-medium ${account.status === 'connected'
                                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                                : account.status === 'expired'
                                                    ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                                                    : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                                            }`}
                                    >
                                        {account.status === 'connected' ? (
                                            <><CheckCircle2 className="w-3 h-3 inline mr-1" />Connected</>
                                        ) : account.status === 'expired' ? (
                                            <><AlertCircle className="w-3 h-3 inline mr-1" />Expired</>
                                        ) : (
                                            <><AlertCircle className="w-3 h-3 inline mr-1" />{account.status}</>
                                        )}
                                    </span>
                                </div>
                                {account.status !== 'connected' && account.reauth_url && (
                                    <a
                                        href={account.reauth_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 mt-2 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                                    >
                                        <ExternalLink className="w-3 h-3" />
                                        Re-authorize
                                    </a>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
