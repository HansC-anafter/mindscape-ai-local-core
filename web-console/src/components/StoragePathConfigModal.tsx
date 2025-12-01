'use client';

import React, { useEffect, useState } from 'react';
import { LocalFilesystemManager } from '@/app/settings/components/wizards/LocalFilesystemManager';

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, { base_path?: string; artifacts_dir?: string }>;
}

interface StoragePathConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspace: Workspace | null;
  workspaceId: string;
  apiUrl: string;
  onSuccess?: () => void;
}

export default function StoragePathConfigModal({
  isOpen,
  onClose,
  workspace,
  workspaceId,
  apiUrl,
  onSuccess
}: StoragePathConfigModalProps) {
  const [workspaceData, setWorkspaceData] = useState<Workspace | null>(workspace);

  // Fetch latest workspace data when modal opens to ensure we have the latest storage_base_path
  useEffect(() => {
    if (isOpen && workspaceId) {
      const fetchWorkspace = async () => {
        try {
          const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
          if (response.ok) {
            const data = await response.json();
            setWorkspaceData(data);
          }
        } catch (err) {
          console.error('Failed to fetch workspace data:', err);
          // Fallback to prop data if fetch fails
          setWorkspaceData(workspace);
        }
      };
      fetchWorkspace();
    } else {
      setWorkspaceData(workspace);
    }
  }, [isOpen, workspaceId, apiUrl, workspace]);

  const handleSuccess = () => {
    if (onSuccess) {
      onSuccess();
    }
    onClose();
  };

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.removeEventListener('keydown', handleEscape);
      };
    }
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <LocalFilesystemManager
      onClose={onClose}
      onSuccess={handleSuccess}
      workspaceMode={true}
      workspaceId={workspaceId}
      apiUrl={apiUrl}
      workspaceTitle={workspaceData?.title}
      initialStorageBasePath={workspaceData?.storage_base_path}
      initialArtifactsDir={workspaceData?.artifacts_dir}
      initialPlaybookStorageConfig={workspaceData?.playbook_storage_config}
    />
  );
}
