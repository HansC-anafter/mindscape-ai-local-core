import React from 'react';

interface RefreshAvatarsCardProps {
    onRefresh: () => void;
    loading: boolean;
    result: {
        summary: {
            refreshed_count: number;
            skipped_count: number;
            failed_count: number;
        };
    } | null;
    error: string | null;
    totalAccounts: number;
}

export function RefreshAvatarsCard({
    onRefresh,
    loading,
    result,
    error,
    totalAccounts,
}: RefreshAvatarsCardProps) {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                Refresh avatars
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                Batch refresh expired avatars (2-3s delay per request, max 50)
            </p>

            <div className="flex items-center gap-3">
                <button
                    onClick={onRefresh}
                    disabled={loading || totalAccounts === 0}
                    className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {loading ? 'Refreshing...' : 'Refresh Expired Avatars'}
                </button>
                {totalAccounts > 0 && (
                    <span className="text-sm text-gray-500">{totalAccounts} accounts</span>
                )}
            </div>

            {loading && (
                <div className="mt-3 text-sm text-blue-600 dark:text-blue-400">
                    ⏳ 刷新中，每個請求間隔 2-3 秒...
                </div>
            )}

            {result && !loading && (
                <div className="mt-3 text-sm space-y-1">
                    <div className="text-green-600 dark:text-green-400">
                        ✅ 已刷新：{result.summary.refreshed_count}
                    </div>
                    <div className="text-gray-500">
                        ⏭️ 跳過（未過期）：{result.summary.skipped_count}
                    </div>
                    {result.summary.failed_count > 0 && (
                        <div className="text-red-600 dark:text-red-400">
                            ❌ 失敗：{result.summary.failed_count}
                        </div>
                    )}
                </div>
            )}

            {error && !loading && (
                <div className="mt-3 text-sm text-red-600 dark:text-red-400">
                    ❌ {error}
                </div>
            )}
        </div>
    );
}
