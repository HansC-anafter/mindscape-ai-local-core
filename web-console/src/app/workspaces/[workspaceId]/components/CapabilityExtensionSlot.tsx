'use client';

import React, { useState, useEffect, Suspense, lazy, useMemo } from 'react';
import { convertImportPathToContextKey, normalizeCapabilityContextKey } from '@/lib/capability-path';
import { getApiBaseUrl } from '@/lib/api-url';

// Use require.context to load capability components (webpack feature)
// @ts-ignore - require.context is a webpack feature
let rawCapabilityComponentsContext: ReturnType<typeof require.context>;
try {
    // @ts-ignore - require.context is a webpack feature
    rawCapabilityComponentsContext = require.context('../../../capabilities', true, /\.tsx$/, 'sync');
} catch {
    rawCapabilityComponentsContext = Object.assign(
        (() => ({})) as any,
        { keys: () => [] as string[], resolve: (k: string) => k, id: '' }
    );
}
const capabilityComponentKeys = new Set<string>(
    typeof rawCapabilityComponentsContext.keys === 'function'
        ? rawCapabilityComponentsContext.keys()
        : []
);
const capabilityComponentsContext = ((key: string) => {
    const normalizedKey = normalizeCapabilityContextKey(key);
    const resolvedKey = normalizedKey && capabilityComponentKeys.has(normalizedKey)
        ? normalizedKey
        : key;
    return rawCapabilityComponentsContext(resolvedKey);
}) as typeof rawCapabilityComponentsContext;

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

    useEffect(() => {
        const loadPanels = async () => {
            try {
                const base = getApiBaseUrl();
                const response = await fetch(
                    `${base}/api/v1/settings/extensions?section=${encodeURIComponent(section)}`
                );
                if (response.ok) {
                    const data = await response.json();
                    console.log('[CapabilityExtensionSlot] Loaded panels:', data.length, data);
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

    // Memoize lazy-loaded components to avoid re-creating on every render
    const lazyComponents = useMemo(() => {
        return panels.map((panel) => {
            const rawContextKey = convertImportPathToContextKey(panel.import_path);
            const contextKey = normalizeCapabilityContextKey(rawContextKey);

            const LazyComponent = lazy(async () => {
                if (!contextKey || !capabilityComponentKeys.has(contextKey)) {
                    console.warn('[CapabilityExtensionSlot] Context key not found:', contextKey);
                    return { default: () => null };
                }
                try {
                    const moduleLoader = capabilityComponentsContext(contextKey);
                    const module = typeof moduleLoader === 'function' ? await moduleLoader() : await moduleLoader;
                    return { default: module[panel.export || 'default'] || module.default };
                } catch (error) {
                    console.error('[CapabilityExtensionSlot] Failed to load component:', panel.component_code, error);
                    return { default: () => null };
                }
            });

            return { panel, LazyComponent };
        });
    }, [panels]);

    if (loading) {
        return (
            <div className="p-3 text-sm text-secondary dark:text-gray-400">
                載入擴充設定中...
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
