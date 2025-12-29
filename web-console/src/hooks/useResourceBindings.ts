'use client';

import { useState, useEffect, useCallback } from 'react';
import { getApiBaseUrl } from '../lib/api-url';

const API_URL = getApiBaseUrl();

export interface WorkspaceResourceBinding {
  workspace_id: string;
  resource_type: 'playbook' | 'tool' | 'data_source';
  resource_id: string;
  access_mode: 'read' | 'write' | 'admin';
  overrides: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface CreateResourceBindingRequest {
  resource_type: 'playbook' | 'tool' | 'data_source';
  resource_id: string;
  access_mode: 'read' | 'write' | 'admin';
  overrides?: Record<string, any>;
}

export interface UpdateResourceBindingRequest {
  access_mode?: 'read' | 'write' | 'admin';
  overrides?: Record<string, any>;
}

interface UseResourceBindingsReturn {
  bindings: WorkspaceResourceBinding[];
  loading: boolean;
  error: string | null;
  loadBindings: () => Promise<void>;
  createBinding: (data: CreateResourceBindingRequest) => Promise<WorkspaceResourceBinding>;
  updateBinding: (resourceType: string, resourceId: string, data: UpdateResourceBindingRequest) => Promise<WorkspaceResourceBinding>;
  deleteBinding: (resourceType: string, resourceId: string) => Promise<void>;
  getBinding: (resourceType: string, resourceId: string) => WorkspaceResourceBinding | undefined;
}

export function useResourceBindings(workspaceId: string): UseResourceBindingsReturn {
  const [bindings, setBindings] = useState<WorkspaceResourceBinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBindings = useCallback(async () => {
    if (!workspaceId) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/resource-bindings/`);
      if (!response.ok) {
        throw new Error(`Failed to load resource bindings: ${response.statusText}`);
      }
      const data = await response.json();
      setBindings(Array.isArray(data) ? data : []);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load resource bindings';
      setError(errorMessage);
      console.error('Failed to load resource bindings:', err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const createBinding = useCallback(async (data: CreateResourceBindingRequest): Promise<WorkspaceResourceBinding> => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/resource-bindings/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Failed to create binding: ${response.statusText}`);
      }

      const binding = await response.json();
      await loadBindings();
      return binding;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create binding';
      setError(errorMessage);
      throw err;
    }
  }, [workspaceId, loadBindings]);

  const updateBinding = useCallback(async (
    resourceType: string,
    resourceId: string,
    data: UpdateResourceBindingRequest
  ): Promise<WorkspaceResourceBinding> => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setError(null);
    try {
      const response = await fetch(
        `${API_URL}/api/v1/workspaces/${workspaceId}/resource-bindings/${resourceType}/${resourceId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Failed to update binding: ${response.statusText}`);
      }

      const binding = await response.json();
      await loadBindings();
      return binding;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update binding';
      setError(errorMessage);
      throw err;
    }
  }, [workspaceId, loadBindings]);

  const deleteBinding = useCallback(async (resourceType: string, resourceId: string): Promise<void> => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setError(null);
    try {
      const response = await fetch(
        `${API_URL}/api/v1/workspaces/${workspaceId}/resource-bindings/${resourceType}/${resourceId}`,
        {
          method: 'DELETE',
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Failed to delete binding: ${response.statusText}`);
      }

      await loadBindings();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete binding';
      setError(errorMessage);
      throw err;
    }
  }, [workspaceId, loadBindings]);

  const getBinding = useCallback((resourceType: string, resourceId: string): WorkspaceResourceBinding | undefined => {
    return bindings.find(
      b => b.resource_type === resourceType && b.resource_id === resourceId
    );
  }, [bindings]);

  useEffect(() => {
    loadBindings();
  }, [loadBindings]);

  return {
    bindings,
    loading,
    error,
    loadBindings,
    createBinding,
    updateBinding,
    deleteBinding,
    getBinding,
  };
}

