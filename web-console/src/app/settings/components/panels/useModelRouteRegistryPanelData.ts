import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '../../../../lib/api-url';
import type {
  ModelRouteRegistryPayload,
  ReconcileResult,
} from './ModelRouteRegistryPanelTypes';

export function useModelRouteRegistryPanelData() {
  const isMountedRef = useRef(true);
  const [payload, setPayload] = useState<ModelRouteRegistryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResult | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const apiUrl = getApiBaseUrl();
      const response = await fetch(`${apiUrl}/api/v1/settings/model-route-registry`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (isMountedRef.current) {
        setPayload(data);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load model route registry');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    void load();
    return () => {
      isMountedRef.current = false;
    };
  }, [load]);

  const reconcile = useCallback(async () => {
    try {
      setReconciling(true);
      setReconcileResult(null);
      const apiUrl = getApiBaseUrl();
      const response = await fetch(`${apiUrl}/api/v1/settings/model-route-registry/reconcile`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setReconcileResult({
        updated_pack_count: Number(data.updated_pack_count || 0),
        updated_runtime_count: Number(data.updated_runtime_count || 0),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reconcile model route registry');
    } finally {
      setReconciling(false);
    }
  }, [load]);

  return {
    payload,
    loading,
    error,
    reconciling,
    reconcileResult,
    reconcile,
  };
}
