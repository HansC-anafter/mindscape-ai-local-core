'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { BaseModal } from '../../../components/BaseModal';
import { WordPressConnectionWizard } from './wizards/WordPressConnectionWizard';
import { NotionConnectionWizard } from './wizards/NotionConnectionWizard';
import { GoogleDriveConnectionWizard } from './wizards/GoogleDriveConnectionWizard';
import { SlackConnectionWizard } from './wizards/SlackConnectionWizard';
import { AirtableConnectionWizard } from './wizards/AirtableConnectionWizard';
import { GoogleSheetsConnectionWizard } from './wizards/GoogleSheetsConnectionWizard';
import { GitHubConnectionWizard } from './wizards/GitHubConnectionWizard';
import { VectorDBConnectionWizard } from './wizards/VectorDBConnectionWizard';
import { LocalFilesystemManager } from './wizards/LocalFilesystemManager';
import { ObsidianConfigWizard } from './wizards/ObsidianConfigWizard';

interface ToolConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  toolType: string | null;
  vectorDBConfig?: any;
  onWizardSuccess: (toolType: string) => void;
}

export function ToolConfigModal({
  isOpen,
  onClose,
  toolType,
  vectorDBConfig,
  onWizardSuccess,
}: ToolConfigModalProps) {
  if (!isOpen || !toolType) return null;

  const handleWizardSuccess = (wizardToolType: string) => {
    onWizardSuccess(wizardToolType);
    onClose();
  };

  const renderWizard = () => {
    switch (toolType) {
      case 'wordpress':
        return (
          <WordPressConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('wordpress')}
          />
        );
      case 'notion':
        return (
          <NotionConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('notion')}
          />
        );
      case 'google_drive':
        return (
          <GoogleDriveConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('google_drive')}
          />
        );
      case 'slack':
        return (
          <SlackConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('slack')}
          />
        );
      case 'airtable':
        return (
          <AirtableConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('airtable')}
          />
        );
      case 'google_sheets':
        return (
          <GoogleSheetsConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('google_sheets')}
          />
        );
      case 'github':
        return (
          <GitHubConnectionWizard
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('github')}
          />
        );
      case 'vector_db':
        return (
          <VectorDBConnectionWizard
            config={vectorDBConfig}
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('vector_db')}
          />
        );
      case 'local_files':
        return (
          <LocalFilesystemManager
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('local_files')}
          />
        );
      case 'obsidian':
        return (
          <ObsidianConfigWizard
            config={null}
            onClose={onClose}
            onSuccess={() => handleWizardSuccess('obsidian')}
          />
        );
      default:
        return (
          <div className="text-center py-8">
            <p className="text-gray-500 dark:text-gray-400">{t('unsupportedToolType' as any)}</p>
            <button
              onClick={onClose}
              className="mt-4 px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600"
            >
              {t('closeButton' as any)}
            </button>
          </div>
        );
    }
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('configureTool' as any)}
      maxWidth="max-w-4xl"
    >
      {renderWizard()}
    </BaseModal>
  );
}
