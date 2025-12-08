'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { BaseModal } from '../../../components/BaseModal';
import { WorkflowWizard } from './wizards/WorkflowWizard';

interface WorkflowConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  platform: string | undefined;
  onWizardSuccess: () => void;
}

export function WorkflowConfigModal({
  isOpen,
  onClose,
  platform,
  onWizardSuccess,
}: WorkflowConfigModalProps) {
  if (!isOpen || !platform) return null;

  const handleWizardSuccess = () => {
    onWizardSuccess();
    onClose();
  };

  const handleWizardClose = () => {
    onClose();
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('configureWorkflow')}
      maxWidth="max-w-4xl"
    >
      <WorkflowWizard
        platform={platform as 'zapier' | 'n8n' | 'make' | 'custom'}
        onClose={handleWizardClose}
        onSuccess={handleWizardSuccess}
      />
    </BaseModal>
  );
}
