import { useCallback, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

interface RefreshResult {
    refreshed: string[];
    skipped: string[];
    failed: string[];
    summary: {
        refreshed_count: number;
        skipped_count: number;
        failed_count: number;
    };
}

/**
 * Hook to batch refresh expired avatars with rate limiting.
 */
export function useAvatarRefresh(params: { apiUrl: string }) {
    const { apiUrl } = params;
    const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<RefreshResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(
        async (usernames: string[], force = false) => {
            setLoading(true);
            setError(null);
            setResult(null);

            try {
                const response = await client.post(`/api/v1/ig/avatar/batch-refresh`, {
                    usernames,
                    force,
                    max_count: 50,
                });

                if (!response.ok) {
                    throw new Error(`Failed: ${response.status} ${response.statusText}`);
                }

                const data: RefreshResult = await response.json();
                setResult(data);
                return data;
            } catch (err) {
                const msg = err instanceof Error ? err.message : 'Unknown error';
                setError(msg);
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [client]
    );

    return { refresh, loading, result, error };
}
