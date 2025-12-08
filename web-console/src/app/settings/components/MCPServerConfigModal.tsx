'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { BaseModal } from '../../../components/BaseModal';
import { MCPServerWizard } from './wizards/MCPServerWizard';

interface MCPServer {
  id: string;
  name: string;
  transport: 'stdio' | 'http';
  status: 'connected' | 'disconnected' | 'error';
  tools_count?: number;
  last_connected?: string;
  error?: string;
}

interface MCPServerConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider: string | undefined;
  editingServer: MCPServer | null;
  onWizardSuccess: () => void;
}

export function MCPServerConfigModal({
  isOpen,
  onClose,
  provider,
  editingServer,
  onWizardSuccess,
}: MCPServerConfigModalProps) {
  if (!isOpen) return null;

  const handleWizardSuccess = () => {
    onWizardSuccess();
    onClose();
  };

  const handleWizardClose = () => {
    onClose();
  };

  const title = editingServer
    ? t('editMCPServer')
    : t('addMCPServer');

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      maxWidth="max-w-4xl"
    >
      <MCPServerWizard
        provider={provider}
        editingServer={editingServer}
        onClose={handleWizardClose}
        onSuccess={handleWizardSuccess}
      />
    </BaseModal>
  );
}
