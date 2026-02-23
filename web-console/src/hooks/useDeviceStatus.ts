'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Device connection info from dispatch manager status API.
 */
export interface DeviceInfo {
    deviceId: string;
    totalClients: number;
    authenticatedClients: number;
    inflightTasks: number;
    pendingTasks: number;
    bridgeControls: number;
    isLocal: boolean;
    lastSeen: number; // Unix timestamp ms
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
    /** Polling interval in milliseconds (default: 10000) */
    pollInterval?: number;
    /** Whether to enable polling (default: true) */
    enabled?: boolean;
}

/**
 * Hook that polls the dispatch manager status endpoint and returns
 * structured device connection information.
 */
export function useDeviceStatus(
    apiUrl: string,
    options: UseDeviceStatusOptions = {},
) {
    const { pollInterval = 10000, enabled = true } = options;
    const [localDevice, setLocalDevice] = useState<DeviceInfo | null>(null);
    const [isPolling, setIsPolling] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchStatus = useCallback(async () => {
        if (!apiUrl) return;
        try {
            setIsPolling(true);
            const res = await fetch(`${apiUrl}/api/v1/mcp/agent/status`);
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
            setError(err instanceof Error ? err.message : 'Connection failed');
        } finally {
            setIsPolling(false);
        }
    }, [apiUrl]);

    useEffect(() => {
        if (!enabled) return;

        // Fetch immediately
        fetchStatus();

        // Set up polling
        timerRef.current = setInterval(fetchStatus, pollInterval);

        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        };
    }, [enabled, pollInterval, fetchStatus]);

    return { localDevice, isPolling, error, refetch: fetchStatus };
}
