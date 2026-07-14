'use client';

import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import {
  createLazySettingsExtensionComponent,
  type SettingsExtensionComponentDescriptor,
} from '@/lib/settings-extension-component-loader';

interface SettingsExtensionPanel extends SettingsExtensionComponentDescriptor {
  title: string;
  requires_workspace_id?: boolean;
  props_schema?: Record<string, unknown>;
}

export interface SettingsExtensionOwnerContract {
  capabilityCode: string;
  componentCode: string;
}

interface CapabilitySettingsExtensionSlotProps {
  section: string;
  workspaceId?: string;
  workspaceScopedOnly?: boolean;
  emptyMessage?: string;
  ownerContract?: SettingsExtensionOwnerContract;
}

const REQUEST_TIMEOUT_MS = 10_000;

export default function CapabilitySettingsExtensionSlot({
  section,
  workspaceId,
  workspaceScopedOnly = false,
  emptyMessage,
  ownerContract,
}: CapabilitySettingsExtensionSlotProps) {
  const [panels, setPanels] = useState<SettingsExtensionPanel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const apiBaseUrl = getApiBaseUrl();
  const requestGenerationRef = useRef(0);
  const ownerCapabilityCode = ownerContract?.capabilityCode;
  const ownerComponentCode = ownerContract?.componentCode;

  useEffect(() => {
    const requestGeneration = ++requestGenerationRef.current;
    const controller = new AbortController();
    let mounted = true;
    let timedOut = false;
    const isCurrentRequest = () => (
      mounted && requestGenerationRef.current === requestGeneration
    );
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    const loadPanels = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ section });
        if (workspaceId) {
          params.set('workspace_id', workspaceId);
        }
        const response = await fetch(
          `${apiBaseUrl}/api/v1/settings/extensions?${params.toString()}`,
          { cache: 'no-store', signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(`Settings extension request failed (${response.status})`);
        }
        const payload = await response.json() as SettingsExtensionPanel[];
        if (timedOut || controller.signal.aborted) {
          throw new DOMException('aborted', 'AbortError');
        }
        if (!isCurrentRequest()) {
          return;
        }
        const scopedPanels = (Array.isArray(payload) ? payload : []).filter((panel) => (
          !workspaceScopedOnly || panel.requires_workspace_id === true
        ));
        if (ownerCapabilityCode && ownerComponentCode && scopedPanels.length > 0) {
          const exactOwner = scopedPanels.length === 1
            && scopedPanels[0]?.capability_code === ownerCapabilityCode
            && scopedPanels[0]?.component_code === ownerComponentCode;
          if (!exactOwner) {
            throw new Error('Settings extension owner contract mismatch');
          }
        }
        setPanels(scopedPanels);
      } catch (requestError) {
        if (isCurrentRequest() && timedOut) {
          setError('Settings extension request timed out');
        } else if (
          isCurrentRequest()
          && !(requestError instanceof DOMException && requestError.name === 'AbortError')
        ) {
          setError(requestError instanceof Error ? requestError.message : 'Failed to load settings extensions');
        }
      } finally {
        window.clearTimeout(timeout);
        if (isCurrentRequest()) {
          setLoading(false);
        }
      }
    };

    void loadPanels();
    return () => {
      mounted = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [
    apiBaseUrl,
    ownerCapabilityCode,
    ownerComponentCode,
    section,
    workspaceId,
    workspaceScopedOnly,
  ]);

  const lazyComponents = useMemo(() => panels.map((panel) => ({
    panel,
    LazyComponent: createLazySettingsExtensionComponent(panel, apiBaseUrl, workspaceId),
  })), [apiBaseUrl, panels, workspaceId]);

  if (loading) {
    return (
      <div role="status" aria-live="polite" className="p-3 text-sm text-secondary dark:text-gray-400">
        Loading extension settings...
      </div>
    );
  }
  if (error) {
    return <div role="alert" className="p-3 text-sm text-red-700 dark:text-red-300">{error}</div>;
  }
  if (panels.length === 0) {
    return emptyMessage ? <div className="p-3 text-sm text-secondary dark:text-gray-400">{emptyMessage}</div> : null;
  }

  return (
    <div data-testid={`capability-settings-extension-slot-${section}`}>
      {lazyComponents.map(({ panel, LazyComponent }) => {
        const props: Record<string, unknown> = { apiUrl: apiBaseUrl };
        if (panel.requires_workspace_id && workspaceId) {
          props.workspaceId = workspaceId;
        }
        return (
          <section
            key={`${panel.capability_code}:${panel.component_code}`}
            className="border-t border-default p-3 first:border-t-0 dark:border-gray-700"
          >
            <Suspense fallback={<div role="status" aria-live="polite" className="py-2 text-sm text-gray-500">Loading {panel.title}...</div>}>
              <LazyComponent {...props} />
            </Suspense>
          </section>
        );
      })}
    </div>
  );
}
