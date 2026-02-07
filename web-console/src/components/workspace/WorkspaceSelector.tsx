'use client';

import React, { useState, useEffect } from 'react';
import { useWorkspaceDataOptional } from '../../contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '../../lib/api-url';

interface Workspace {
  id: string;
  title: string;
  description?: string;
  workspace_type?: string;
}

interface WorkspaceSelectorProps {
  ownerUserId?: string;
  groupId?: string;
  value?: string;
  onValueChange?: (workspaceId: string) => void;
  showLabel?: boolean;
  className?: string;
}

export function WorkspaceSelector({
  ownerUserId,
  groupId,
  value,
  onValueChange,
  showLabel = true,
  className = ''
}: WorkspaceSelectorProps) {
  const workspaceData = useWorkspaceDataOptional();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get owner_user_id (priority: props > context > default)
  const effectiveOwnerUserId = ownerUserId ||
    (workspaceData as any)?.user?.id ||
    'default-user';

  // Get current workspace ID (priority: props > context > default)
  const currentWorkspaceId = value ||
    workspaceData?.workspace?.id ||
    'test-ws';

  useEffect(() => {
    const fetchWorkspaces = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Build API URL
        const params = new URLSearchParams({
          owner_user_id: effectiveOwnerUserId,
          limit: '50',
          include_system: 'false'
        });

        // Cloud: optional group_id filter
        if (groupId) {
          params?.append('group_id', groupId);
        }

        const apiUrl = getApiBaseUrl();
        const url = `${apiUrl}/api/v1/workspaces?${params?.toString()}`;
        console.log('[WorkspaceSelector] Fetching workspaces from:', url);

        const response = await fetch(url, {
          headers: {
            'Content-Type': 'application/json',
            // Cloud: get from context or env var
            'X-Tenant-UUID': process.env.NEXT_PUBLIC_TENANT_ID || 'local-default-tenant'
          }
        });

        console.log('[WorkspaceSelector] Response status:', response.status, response.statusText);

        if (!response.ok) {
          throw new Error(`Failed to fetch workspaces: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[WorkspaceSelector] Received data:', data);
        const workspaceList = Array.isArray(data) ? data : [];
        console.log('[WorkspaceSelector] Workspace list:', workspaceList.length, 'workspaces');

        setWorkspaces(workspaceList);

        // Auto-select if only one workspace
        if (workspaceList.length === 1 && onValueChange) {
          onValueChange(workspaceList[0].id);
        }
      } catch (err) {
        console.error('[WorkspaceSelector] Error fetching workspaces:', err);
        const errorMessage = err instanceof Error ? err.message : 'Failed to load workspaces';
        setError(errorMessage);
        // Log detailed error for debugging
        if (err instanceof Error) {
          console.error('[WorkspaceSelector] Error details:', {
            message: err.message,
            stack: err.stack,
            name: err.name
          });
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchWorkspaces();
  }, [effectiveOwnerUserId, groupId, onValueChange]);

  // Progressive enhancement: hide selector when only one workspace
  if (!isLoading && workspaces.length <= 1) {
    return null;
  }

  // Show selector when multiple workspaces
  return (
    <div className={className}>
      {showLabel && (
        <label className="block text-sm font-medium mb-2 text-foreground">
          選擇工作區
        </label>
      )}
      <select
        value={currentWorkspaceId}
        onChange={(e) => {
          if (onValueChange) {
            onValueChange(e.target.value);
          }
        }}
        disabled={isLoading}
        className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? (
          <option value="">載入中...</option>
        ) : (
          <>
            <option value="">請選擇工作區</option>
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id}>
                {ws.title} {ws.description ? `- ${ws.description}` : ''}
              </option>
            ))}
          </>
        )}
      </select>
      {error && (
        <div className="mt-1">
          <p className="text-sm text-destructive">{error}</p>
          <p className="text-xs text-gray-500 mt-1">
            請檢查瀏覽器控制台以獲取詳細錯誤信息
          </p>
        </div>
      )}
    </div>
  );
}

