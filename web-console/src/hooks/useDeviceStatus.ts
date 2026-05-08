'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

export interface DeviceInfo {
    deviceId: string;
    totalClients: number;
    authenticatedClients: number;
    inflightTasks: number;
    pendingTasks: number;
    bridgeControls: number;
    isLocal: boolean;
    lastSeen: number;
}

interface DispatchStatus {
    device_id: string;
    connected_workspaces: number;
    total_clients: number;
    authenticated_clients: number;
    bridge_controls: number;
    inflight_tasks: number;
    pending_tasks: number;
    workspaces: Record<string, {
        clients: Array<{
            client_id: string;
            surface_type: string;
            authenticated: boolean;
            last_heartbeat?: number;
        }>;
        pending_count: number;
    }>;
    bridges: Array<{
        bridge_id: string;
        owner_user_id: string;
    }>;
}

interface UseDeviceStatusOptions {
    pollInterval?: number;
    enabled?: boolean;
}

export function useDeviceStatus(
    apiUrl: string,
    options: UseDeviceStatusOptions = {},
) {
    const { pollInterval = 10000, enabled = true } = options;
    const [localDevice, setLocalDevice] = useState<DeviceInfo | null>(null);
    const [isPolling, setIsPolling] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const inFlightRef = useRef<Promise<void> | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const fetchStatus = useCallback(async () => {
        if (apiUrl == null) return;
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
        if (inFlightRef.current) return inFlightRef.current;

        const request = (async () => {
            try {
                setIsPolling(true);
                const controller = new AbortController();
                abortControllerRef.current = controller;
                const res = await fetch(`${apiUrl}/api/v1/mcp/agent/status`, {
                    signal: controller.signal,
                });
                if (!res.ok) {
                    setError(`Status API returned ${res.status}`);
                    return;
                }
                const data: DispatchStatus = await res.json();

                const device: DeviceInfo = {
                    deviceId: data.device_id,
                    totalClients: data.total_clients,
                    authenticatedClients: data.authenticated_clients,
                    inflightTasks: data.inflight_tasks,
                    pendingTasks: data.pending_tasks,
                    bridgeControls: data.bridge_controls,
                    isLocal: true,
                    lastSeen: Date.now(),
                };

                setLocalDevice(device);
                setError(null);
            } catch (err) {
                if (err instanceof Error && err.name === 'AbortError') return;
                setError(err instanceof Error ? err.message : 'Connection failed');
            } finally {
                setIsPolling(false);
                abortControllerRef.current = null;
            }
        })();

        inFlightRef.current = request;
        try {
            await request;
        } finally {
            if (inFlightRef.current === request) {
                inFlightRef.current = null;
            }
        }
    }, [apiUrl]);

    useEffect(() => {
        if (!enabled) return;

        fetchStatus();

        timerRef.current = setInterval(fetchStatus, pollInterval);

        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
            abortControllerRef.current?.abort();
            abortControllerRef.current = null;
            inFlightRef.current = null;
        };
    }, [enabled, pollInterval, fetchStatus]);

    return { localDevice, isPolling, error, refetch: fetchStatus };
}
