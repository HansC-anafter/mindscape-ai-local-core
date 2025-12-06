'use client';

import { useState, useCallback } from 'react';
import { useResourceBindings } from './useResourceBindings';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ToolOverlay {
  tool_whitelist?: string[];
  danger_level_override?: 'low' | 'medium' | 'high';
  enabled?: boolean;
}

export interface ToolWithOverlay {
  tool_id: string;
  tool_name: string;
  original_danger_level: 'low' | 'medium' | 'high';
  effective_danger_level: 'low' | 'medium' | 'high';
  enabled: boolean;
  overlay_applied: boolean;
}

interface UseToolOverlayReturn {
  overlay: ToolOverlay | null;
  loading: boolean;
  error: string | null;
  tools: ToolWithOverlay[];
  loadTools: () => Promise<void>;
  updateOverlay: (overlay: Partial<ToolOverlay>) => Promise<void>;
  validateDangerLevel: (original: string, override: string) => boolean;
}

const DANGER_LEVEL_ORDER: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

export function useToolOverlay(workspaceId: string): UseToolOverlayReturn {
  const { bindings, getBinding, updateBinding, createBinding } = useResourceBindings(workspaceId);
  const [tools, setTools] = useState<ToolWithOverlay[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toolBinding = getBinding('tool', 'workspace-tools');

  const overlay: ToolOverlay | null = toolBinding
    ? {
        tool_whitelist: toolBinding.overrides?.tool_whitelist,
        danger_level_override: toolBinding.overrides?.danger_level_override,
        enabled: toolBinding.overrides?.enabled,
      }
    : null;

  const validateDangerLevel = useCallback((original: string, override: string): boolean => {
    const originalLevel = DANGER_LEVEL_ORDER[original.toLowerCase()] || 0;
    const overrideLevel = DANGER_LEVEL_ORDER[override.toLowerCase()] || 0;
    return overrideLevel >= originalLevel;
  }, []);

  const loadTools = useCallback(async () => {
    if (!workspaceId) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/tools/?workspace_id=${workspaceId}`);
      if (!response.ok) {
        throw new Error(`Failed to load tools: ${response.statusText}`);
      }
      const data = await response.json();
      const toolsList = Array.isArray(data) ? data : [];

      const toolsWithOverlay: ToolWithOverlay[] = toolsList.map((tool: any) => {
        const originalDangerLevel = tool.danger_level || 'medium';
        const effectiveDangerLevel = overlay?.danger_level_override || originalDangerLevel;
        const isEnabled = overlay?.enabled !== undefined ? overlay.enabled : tool.enabled !== false;
        const overlayApplied = !!toolBinding;

        return {
          tool_id: tool.tool_id || tool.id,
          tool_name: tool.name || tool.tool_name,
          original_danger_level: originalDangerLevel,
          effective_danger_level: effectiveDangerLevel,
          enabled: isEnabled,
          overlay_applied: overlayApplied,
        };
      });

      if (overlay?.tool_whitelist && overlay.tool_whitelist.length > 0) {
        const whitelistSet = new Set(overlay.tool_whitelist);
        setTools(toolsWithOverlay.filter(t => whitelistSet.has(t.tool_id)));
      } else {
        setTools(toolsWithOverlay);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load tools';
      setError(errorMessage);
      console.error('Failed to load tools:', err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, overlay, toolBinding]);

  const updateOverlay = useCallback(async (newOverlay: Partial<ToolOverlay>): Promise<void> => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setError(null);
    try {
      const currentOverrides = toolBinding?.overrides || {};
      const updatedOverrides = {
        ...currentOverrides,
        ...newOverlay,
      };

      if (toolBinding) {
        await updateBinding('tool', 'workspace-tools', {
          overrides: updatedOverrides,
        });
      } else {
        await createBinding({
          resource_type: 'tool',
          resource_id: 'workspace-tools',
          access_mode: 'admin',
          overrides: updatedOverrides,
        });
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update tool overlay';
      setError(errorMessage);
      throw err;
    }
  }, [workspaceId, toolBinding, updateBinding, createBinding]);

  return {
    overlay,
    loading,
    error,
    tools,
    loadTools,
    updateOverlay,
    validateDangerLevel,
  };
}

