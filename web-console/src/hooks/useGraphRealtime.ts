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

        const apiBase = getApiBaseUrl();
        const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws';
        const wsHost = apiBase.replace(/^https?:\/\//, '');
        const wsUrl = `${wsProtocol}://${wsHost}/ws/graph/${workspaceId}`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                setIsConnected(true);
                onConnect?.();
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as GraphChangeEvent;
                    setLastEvent(data);
                    onChangeEvent?.(data);
                } catch {
                    onError?.(event as unknown as Event);
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                onDisconnect?.();

                if (enabled) {
                    reconnectTimeoutRef.current = setTimeout(() => {
                        connect();
                    }, 5000);
                }
            };

            ws.onerror = (error) => {
                onError?.(error);
            };

            wsRef.current = ws;
        } catch {
            onError?.(new Event('error'));
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
