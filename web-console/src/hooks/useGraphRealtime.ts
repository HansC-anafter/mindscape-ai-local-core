/**
 * useGraphRealtime - WebSocket hook for real-time graph updates
 *
 * Connects to the backend WebSocket for receiving graph change notifications.
 * Automatically refreshes the graph and pending changes when updates occur.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';

export interface GraphChangeEvent {
    type: 'change_created' | 'change_applied' | 'change_rejected' | 'change_undone';
    workspace_id: string;
    change_id: string;
    operation?: string;
    target_type?: string;
    target_id?: string;
    actor?: string;
}

export interface UseGraphRealtimeOptions {
    workspaceId: string;
    enabled?: boolean;
    onChangeEvent?: (event: GraphChangeEvent) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: Event) => void;
}

export function useGraphRealtime({
    workspaceId,
    enabled = true,
    onChangeEvent,
    onConnect,
    onDisconnect,
    onError,
}: UseGraphRealtimeOptions) {
    const wsRef = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [lastEvent, setLastEvent] = useState<GraphChangeEvent | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (!enabled || !workspaceId) return;

        // Build WebSocket URL
        const apiBase = getApiBaseUrl();
        const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws';
        const wsHost = apiBase.replace(/^https?:\/\//, '');
        const wsUrl = `${wsProtocol}://${wsHost}/ws/graph/${workspaceId}`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('[useGraphRealtime] Connected to', wsUrl);
                setIsConnected(true);
                onConnect?.();
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as GraphChangeEvent;
                    console.log('[useGraphRealtime] Received event:', data);
                    setLastEvent(data);
                    onChangeEvent?.(data);
                } catch (e) {
                    console.error('[useGraphRealtime] Failed to parse message:', e);
                }
            };

            ws.onclose = () => {
                console.log('[useGraphRealtime] Disconnected');
                setIsConnected(false);
                onDisconnect?.();

                // Attempt to reconnect after 5 seconds
                if (enabled) {
                    reconnectTimeoutRef.current = setTimeout(() => {
                        console.log('[useGraphRealtime] Attempting to reconnect...');
                        connect();
                    }, 5000);
                }
            };

            ws.onerror = (error) => {
                console.error('[useGraphRealtime] WebSocket error:', error);
                onError?.(error);
            };

            wsRef.current = ws;
        } catch (e) {
            console.error('[useGraphRealtime] Failed to connect:', e);
        }
    }, [workspaceId, enabled, onChangeEvent, onConnect, onDisconnect, onError]);

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        setIsConnected(false);
    }, []);

    // Connect on mount, disconnect on unmount
    useEffect(() => {
        if (enabled && workspaceId) {
            connect();
        }

        return () => {
            disconnect();
        };
    }, [workspaceId, enabled, connect, disconnect]);

    return {
        isConnected,
        lastEvent,
        reconnect: connect,
        disconnect,
    };
}

export default useGraphRealtime;
