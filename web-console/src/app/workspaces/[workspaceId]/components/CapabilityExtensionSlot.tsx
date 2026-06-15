'use client';

import React, { useState, useEffect, Suspense, useMemo } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import { createLazySettingsExtensionComponent } from '@/lib/settings-extension-component-loader';

interface SettingsExtensionPanel {
    capability_code: string;
    component_code: string;
    title: string;
    description?: string;
    requires_workspace_id?: boolean;
    show_when?: {
        runtime_codes?: string[];
    };
    props_schema?: Record<string, any>;
    import_path: string;
    export: string;
}

interface CapabilityExtensionSlotProps {
    section: string;
    workspaceId: string;
}

export default function CapabilityExtensionSlot({ section, workspaceId }: CapabilityExtensionSlotProps) {
    const [panels, setPanels] = useState<SettingsExtensionPanel[]>([]);
    const [loading, setLoading] = useState(true);
    const apiBaseUrl = getApiBaseUrl();

    useEffect(() => {
        const loadPanels = async () => {
            try {
                const base = getApiBaseUrl();
                const params = new URLSearchParams({ section });
                if (workspaceId) {
                    params.set('workspace_id', workspaceId);
                }
                const response = await fetch(
                    `${base}/api/v1/settings/extensions?${params.toString()}`
                );
                if (response.ok) {
                    const data = await response.json();
                    setPanels(data);
                } else {
                    console.warn('[CapabilityExtensionSlot] API response not ok:', response.status);
                }
            } catch (error) {
                console.error('[CapabilityExtensionSlot] Failed to load panels:', error);
            } finally {
                setLoading(false);
            }
        };
        loadPanels();
    }, [section]);

    const lazyComponents = useMemo(() => {
        return panels.map((panel) => {
            const LazyComponent = createLazySettingsExtensionComponent(panel, apiBaseUrl);

            return { panel, LazyComponent };
        });
    }, [apiBaseUrl, panels]);

    if (loading) {
        return (
            <div className="p-3 text-sm text-secondary dark:text-gray-400">
                Loading extension settings...
            </div>
        );
    }

    if (panels.length === 0) return null;

    return (
        <>
            {lazyComponents.map(({ panel, LazyComponent }) => {
                const props: Record<string, any> = {};
                if (panel.requires_workspace_id) {
                    props.workspaceId = workspaceId;
                }
                props.apiUrl = apiBaseUrl;

                return (
                    <div key={`${panel.capability_code}:${panel.component_code}`} className="border-t dark:border-gray-700 p-3">
                        <Suspense fallback={
                            <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                                Loading {panel.title}...
                            </div>
                        }>
                            <LazyComponent {...props} />
                        </Suspense>
                    </div>
                );
            })}
        </>
    );
}
