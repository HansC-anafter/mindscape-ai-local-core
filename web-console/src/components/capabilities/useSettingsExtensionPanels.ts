'use client';

import { useEffect, useRef, useState } from 'react';

import type { SettingsExtensionComponentDescriptor } from '@/lib/settings-extension-component-loader';

export interface SettingsExtensionPanel extends SettingsExtensionComponentDescriptor {
  title: string;
  requires_workspace_id?: boolean;
  props_schema?: Record<string, unknown>;
}

export interface SettingsExtensionOwnerContract {
  capabilityCode: string;
  componentCode: string;
}

interface UseSettingsExtensionPanelsOptions {
  apiBaseUrl: string;
  section: string;
  workspaceId?: string;
  workspaceScopedOnly: boolean;
  ownerContract?: SettingsExtensionOwnerContract;
}

interface SettingsExtensionPanelsState {
  panels: SettingsExtensionPanel[];
  loading: boolean;
  error: string | null;
}

const REQUEST_TIMEOUT_MS = 10_000;

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function useSettingsExtensionPanels({
  apiBaseUrl,
  section,
  workspaceId,
  workspaceScopedOnly,
  ownerContract,
}: UseSettingsExtensionPanelsOptions): SettingsExtensionPanelsState {
  const [panels, setPanels] = useState<SettingsExtensionPanel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);
  const ownerCapabilityCode = ownerContract?.capabilityCode.trim();
  const ownerComponentCode = ownerContract?.componentCode.trim();
  const hasOwnerContract = ownerContract !== undefined;

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
      setPanels([]);
      try {
        if (hasOwnerContract && (!ownerCapabilityCode || !ownerComponentCode)) {
          throw new Error('Settings extension owner contract is incomplete');
        }
        const params = new URLSearchParams({ section });
        if (workspaceId) {
          params.set('workspace_id', workspaceId);
        }
        if (hasOwnerContract) {
          params.set('capability_code', ownerCapabilityCode as string);
          params.set('component_code', ownerComponentCode as string);
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
        if (hasOwnerContract && !Array.isArray(payload)) {
          throw new Error('Settings extension owner response is invalid');
        }
        const responsePanels = Array.isArray(payload) ? payload : [];
        if (hasOwnerContract && responsePanels.length > 0) {
          const exactOwner = responsePanels.length === 1
            && responsePanels[0]?.capability_code === ownerCapabilityCode
            && responsePanels[0]?.component_code === ownerComponentCode;
          if (!exactOwner) {
            throw new Error('Settings extension owner contract mismatch');
          }
        }
        const scopedPanels = responsePanels.filter((panel) => (
          !workspaceScopedOnly || panel.requires_workspace_id === true
        ));
        setPanels(scopedPanels);
      } catch (requestError) {
        if (isCurrentRequest() && timedOut) {
          setError('Settings extension request timed out');
        } else if (isCurrentRequest() && !isAbortError(requestError)) {
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
    hasOwnerContract,
    ownerCapabilityCode,
    ownerComponentCode,
    section,
    workspaceId,
    workspaceScopedOnly,
  ]);

  return { panels, loading, error };
}
