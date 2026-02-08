'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { t } from '../../../../lib/i18n';
import { showNotification } from '../../hooks/useSettingsNotification';

interface ModelFile {
    filename: string;
    expected_hash: string;
    size_bytes: number;
}

interface LocalModel {
    model_id: string;
    display_name: string;
    pack_code: string;
    status: 'not_downloaded' | 'downloading' | 'downloaded' | 'verified' | 'corrupted';
    is_downloaded: boolean;
    is_verified: boolean;
    size_bytes: number;
    local_path: string | null;
    license_spdx: string;
    hardware_min_vram_gb: number;
    download_progress?: number;
    manual_download_url?: string;
}

interface DiskUsage {
    pack_code: string;
    usage_bytes: Record<string, number>;
    usage_human: string;
}

const STATUS_LABELS: Record<string, { label: string; color: string; icon: string }> = {
    not_downloaded: { label: 'Not Downloaded', color: 'text-gray-500', icon: '⏳' },
    downloading: { label: 'Downloading...', color: 'text-blue-500', icon: '↓' },
    downloaded: { label: 'Downloaded', color: 'text-yellow-500', icon: '✓' },
    verified: { label: 'Ready', color: 'text-green-500', icon: '✓' },
    corrupted: { label: 'Corrupted', color: 'text-red-500', icon: '⚠' },
};

export function LocalModelsPanel() {
    const [models, setModels] = useState<LocalModel[]>([]);
    const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null);
    const [loading, setLoading] = useState(true);
    const [downloadingModels, setDownloadingModels] = useState<Set<string>>(new Set());

    const loadModels = useCallback(async () => {
        try {
            // Try loading from LAF capability
            const response = await fetch('/api/v1/capabilities/layer_asset_forge/models');
            if (response.ok) {
                const data = await response.json();
                setModels(data.models || []);
                setDiskUsage({
                    pack_code: data.pack_code,
                    usage_bytes: {},
                    usage_human: formatBytes(data.total_disk_usage_bytes || 0),
                });
            }
        } catch (error) {
            console.error('Failed to load local models:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadModels();
    }, [loadModels]);

    const formatBytes = (bytes: number): string => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const handleDownload = async (modelId: string) => {
        setDownloadingModels(prev => new Set(prev).add(modelId));

        try {
            const response = await fetch(
                `/api/v1/capabilities/layer_asset_forge/models/${modelId}/download`,
                { method: 'POST' }
            );

            if (response.ok) {
                showNotification('success', `Model ${modelId} downloaded successfully`);
                loadModels();
            } else {
                const error = await response.json();
                showNotification('error', `Failed to download model: ${error.detail}`);
            }
        } catch (error) {
            showNotification('error', `Download failed: ${error}`);
        } finally {
            setDownloadingModels(prev => {
                const next = new Set(prev);
                next.delete(modelId);
                return next;
            });
        }
    };

    const handleDelete = async (modelId: string) => {
        if (!confirm(`Delete model ${modelId}? This will free up disk space but the model will need to be re-downloaded for use.`)) {
            return;
        }

        try {
            const response = await fetch(
                `/api/v1/capabilities/layer_asset_forge/models/${modelId}`,
                { method: 'DELETE' }
            );

            if (response.ok) {
                showNotification('success', `Model ${modelId} deleted`);
                loadModels();
            } else {
                const error = await response.json();
                showNotification('error', `Failed to delete model: ${error.detail}`);
            }
        } catch (error) {
            showNotification('error', `Delete failed: ${error}`);
        }
    };

    if (loading) {
        return (
            <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                Loading local models...
            </div>
        );
    }

    if (models.length === 0) {
        return (
            <div className="text-sm text-gray-500 dark:text-gray-400 py-4">
                No local models configured. Install a capability pack that requires local models.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary */}
            <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div>
                    <h4 className="font-medium text-gray-900 dark:text-white">
                        {t('localModels' as any) || 'Local ML Models'}
                    </h4>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        {models.filter(m => m.is_verified).length} of {models.length} models ready
                    </p>
                </div>
                <div className="text-right">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {diskUsage?.usage_human || '0 B'}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Disk Usage
                    </p>
                </div>
            </div>

            {/* Model List */}
            <div className="space-y-4">
                {models.map((model) => {
                    const statusInfo = STATUS_LABELS[model.status] || STATUS_LABELS.not_downloaded;
                    const isDownloading = downloadingModels.has(model.model_id);

                    return (
                        <div
                            key={model.model_id}
                            className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
                        >
                            <div className="flex items-start justify-between">
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <h5 className="font-medium text-gray-900 dark:text-white">
                                            {model.display_name}
                                        </h5>
                                        <span className={`text-sm ${statusInfo.color}`}>
                                            {statusInfo.icon} {statusInfo.label}
                                        </span>
                                    </div>
                                    <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                                        <span>Size: {formatBytes(model.size_bytes)}</span>
                                        <span className="mx-2">•</span>
                                        <span>License: {model.license_spdx}</span>
                                        <span className="mx-2">•</span>
                                        <span>Min VRAM: {model.hardware_min_vram_gb} GB</span>
                                    </div>
                                    {model.local_path && (
                                        <div className="mt-1 text-xs text-gray-400 dark:text-gray-500 font-mono truncate">
                                            {model.local_path}
                                        </div>
                                    )}
                                </div>

                                <div className="flex items-center gap-2 ml-4">
                                    {!model.is_downloaded && !isDownloading && (
                                        <>
                                            {model.manual_download_url ? (
                                                <a
                                                    href={model.manual_download_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="px-3 py-1.5 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500"
                                                >
                                                    Manual Download
                                                </a>
                                            ) : (
                                                <button
                                                    onClick={() => handleDownload(model.model_id)}
                                                    className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                                >
                                                    Download
                                                </button>
                                            )}
                                        </>
                                    )}

                                    {isDownloading && (
                                        <div className="flex items-center gap-2">
                                            <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />
                                            <span className="text-sm text-blue-500">Downloading...</span>
                                        </div>
                                    )}

                                    {model.is_downloaded && (
                                        <button
                                            onClick={() => handleDelete(model.model_id)}
                                            className="px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 dark:bg-red-900/20 rounded-md hover:bg-red-100 dark:hover:bg-red-900/30 focus:outline-none focus:ring-2 focus:ring-red-500"
                                        >
                                            Delete
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Download Progress Bar */}
                            {isDownloading && model.download_progress !== undefined && (
                                <div className="mt-3">
                                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                        <div
                                            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                            style={{ width: `${(model.download_progress || 0) * 100}%` }}
                                        />
                                    </div>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                        {Math.round((model.download_progress || 0) * 100)}%
                                    </p>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Info */}
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <div className="flex items-start gap-2">
                    <span className="text-blue-500">ℹ</span>
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                        <p className="font-medium">About Local Models</p>
                        <p className="mt-1">
                            Local models are downloaded to your machine for offline inference.
                            They require disk space and sufficient GPU memory (VRAM) for optimal performance.
                            CPU fallback is available for most models but will be slower.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default LocalModelsPanel;
