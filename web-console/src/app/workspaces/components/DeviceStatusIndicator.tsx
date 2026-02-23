'use client';

import React from 'react';
import { useDeviceStatus, type DeviceInfo } from '@/hooks/useDeviceStatus';
import styles from './DeviceStatusIndicator.module.css';

interface DeviceStatusIndicatorProps {
    /** Backend API URL (e.g. http://localhost:8000) */
    apiUrl: string;
    /** Show detailed metrics (default: false) */
    showDetails?: boolean;
    /** Custom class name */
    className?: string;
}

/**
 * Shows device connection status with a colored dot indicator.
 *
 * States:
 *   🟢 Connected — device has authenticated clients
 *   🟡 Idle — device reachable but no clients connected
 *   🔴 Offline — cannot reach status endpoint
 */
export function DeviceStatusIndicator({
    apiUrl,
    showDetails = false,
    className = '',
}: DeviceStatusIndicatorProps) {
    const { localDevice, error } = useDeviceStatus(apiUrl);

    const status = getStatus(localDevice, error);

    return (
        <div className={`${styles.container} ${className}`} title={status.tooltip}>
            <span className={`${styles.dot} ${styles[status.color]}`} />
            <span className={styles.label}>{status.label}</span>
            {showDetails && localDevice && (
                <span className={styles.details}>
                    {localDevice.authenticatedClients} client{localDevice.authenticatedClients !== 1 ? 's' : ''}
                    {localDevice.inflightTasks > 0 && ` · ${localDevice.inflightTasks} inflight`}
                    {localDevice.pendingTasks > 0 && ` · ${localDevice.pendingTasks} pending`}
                </span>
            )}
        </div>
    );
}

interface StatusInfo {
    color: 'green' | 'yellow' | 'red';
    label: string;
    tooltip: string;
}

function getStatus(device: DeviceInfo | null, error: string | null): StatusInfo {
    if (error || !device) {
        return {
            color: 'red',
            label: 'Offline',
            tooltip: error || 'Cannot reach dispatch manager',
        };
    }

    if (device.authenticatedClients > 0) {
        return {
            color: 'green',
            label: device.deviceId,
            tooltip: `Connected: ${device.authenticatedClients} authenticated client(s), ${device.inflightTasks} inflight`,
        };
    }

    return {
        color: 'yellow',
        label: device.deviceId,
        tooltip: `Idle: dispatch manager reachable but no clients connected`,
    };
}
