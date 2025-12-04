'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { StatusPill } from './StatusPill';
import type { CapabilityPack, ToolStatus } from '../types';

interface PackCardProps {
  pack: CapabilityPack;
  onInstall: () => void;
  installing: boolean;
  getToolStatus: (toolType: string) => ToolStatus;
}

function getPackName(packId: string): string {
  const nameMap: Record<string, string> = {
    product_designer: t('packProductDesignerName'),
    content_creator: t('packContentCreatorName'),
    wordpress_webmaster: t('packWordPressWebmasterName'),
  };
  return nameMap[packId] || packId;
}

function getPackDescription(packId: string): string {
  const descMap: Record<string, string> = {
    product_designer: t('packProductDesignerDescription'),
    content_creator: t('packContentCreatorDescription'),
    wordpress_webmaster: t('packWordPressWebmasterDescription'),
  };
  return descMap[packId] || '';
}

function getPackCapabilities(packId: string): string[] {
  const capMap: Record<string, string[]> = {
    product_designer: [
      t('packProductDesignerCap1'),
      t('packProductDesignerCap2'),
      t('packProductDesignerCap3'),
    ],
    content_creator: [
      t('packContentCreatorCap1'),
      t('packContentCreatorCap2'),
      t('packContentCreatorCap3'),
    ],
    wordpress_webmaster: [
      t('packWordPressWebmasterCap1'),
      t('packWordPressWebmasterCap2'),
      t('packWordPressWebmasterCap3'),
      t('packWordPressWebmasterCap4'),
    ],
  };
  return capMap[packId] || [];
}

export function PackCard({ pack, onInstall, installing, getToolStatus }: PackCardProps) {
  const packName = getPackName(pack.id);
  const packDescription = getPackDescription(pack.id) || pack.description;
  const packCapabilities = getPackCapabilities(pack.id);
  const displayPlaybooks = pack.playbooks || [];
  const displayTools = pack.tools || pack.required_tools || [];

  return (
    <Card hover className="flex flex-col h-full">
      <div className="flex items-start space-x-3 mb-4 flex-shrink-0">
        {pack.icon && <span className="text-2xl flex-shrink-0">{pack.icon}</span>}
        <div className="flex-1 min-w-0">
          {/* Status, Version, Date - Above name */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            {pack.installed && (
              <span className="px-2 py-1 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded font-medium whitespace-nowrap">
                {t('installed')}
              </span>
            )}
            {pack.enabled_by_default && !pack.installed && (
              <span className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded font-medium whitespace-nowrap">
                {t('default')}
              </span>
            )}
            {(pack.version || pack.installed_at) && (
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 flex-wrap">
                {pack.version && <span className="whitespace-nowrap">v{pack.version}</span>}
                {pack.installed_at && (
                  <span className="whitespace-nowrap">
                    {t('installedAt')}: {new Date(pack.installed_at).toLocaleDateString('zh-TW')}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Name */}
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1.5 leading-tight">{pack.name || packName}</h3>

          {/* Description */}
          {packDescription && (
            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{packDescription}</p>
          )}
        </div>
      </div>

      <div className="space-y-3 mb-4 flex-1 min-h-0">
        {pack.ai_members && pack.ai_members.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('packInstallsMembers')}:</p>
            <div className="flex flex-wrap gap-2">
              {pack.ai_members.map((member) => (
                <span
                  key={member}
                  className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 rounded"
                >
                  {member}
                </span>
              ))}
            </div>
          </div>
        )}

        {displayPlaybooks.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('packInstallsPlaybooks')}:</p>
            <div className="flex flex-wrap gap-2">
              {displayPlaybooks.map((playbook, idx) => (
                <span
                  key={idx}
                  className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded"
                >
                  {playbook}
                </span>
              ))}
            </div>
          </div>
        )}

        {displayTools.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('packProvidesTools')}:</p>
            <div className="flex flex-wrap gap-2">
              {displayTools.map((tool, idx) => (
                <span
                  key={idx}
                  className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}

        {pack.routes && pack.routes.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('packProvidesRoutes')}:</p>
            <div className="text-xs text-gray-600 dark:text-gray-400">
              {pack.routes.length} {t('apiRoutes')}
            </div>
          </div>
        )}

        {packCapabilities.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('mainCapabilities')}:</p>
            <div className="flex flex-wrap gap-2">
              {packCapabilities.map((capability, idx) => (
                <span
                  key={idx}
                  className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded"
                >
                  {capability}
                </span>
              ))}
            </div>
          </div>
        )}

        {pack.required_tools && pack.required_tools.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('requiredToolsLabel')}</p>
            <div className="space-y-2">
              {pack.required_tools.map((toolType) => {
              const status = getToolStatus(toolType);
              const toolInfo = pack.required_tools_info?.[toolType];
              const toolName = toolInfo?.name || (
                toolType === 'wordpress'
                  ? 'WordPress'
                  : toolType === 'notion'
                    ? 'Notion'
                    : toolType === 'google_drive'
                      ? 'Google Drive'
                      : toolType === 'obsidian'
                        ? 'Obsidian'
                        : toolType === 'vector_db'
                          ? 'PostgreSQL / pgvector'
                          : toolType
              );
              const isConfigured = status.status === 'connected' || status.status === 'local';

              return (
                <div key={toolType} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-700 dark:text-gray-300 font-medium">{toolName}</span>
                    <StatusPill
                      status={isConfigured ? 'enabled' : 'disabled'}
                      label={status.label}
                      icon={status.icon}
                    />
                  </div>
                  {!isConfigured && toolInfo && (
                    <div className="pl-2 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                      {toolInfo.description && (
                        <p className="text-gray-500 dark:text-gray-400">{toolInfo.description}</p>
                      )}
                      <div className="flex flex-wrap gap-2">
                        {toolInfo.official_url && (
                          <a
                            href={toolInfo.official_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
                          >
                            {t('officialWebsite')}
                          </a>
                        )}
                        {toolInfo.download_url && (
                          <a
                            href={toolInfo.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
                          >
                            {t('download')}
                          </a>
                        )}
                        {toolInfo.local_setup_guide && (
                          <a
                            href={toolInfo.local_setup_guide}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
                          >
                            {t('setupGuide')}
                          </a>
                        )}
                        {toolInfo.api_docs && (
                          <a
                            href={toolInfo.api_docs}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
                          >
                            {t('apiDocs')}
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            </div>
          </div>
        )}
      </div>

      <button
        onClick={onInstall}
        disabled={installing || pack.installed}
        className={`w-full py-2 rounded-md font-medium mt-auto flex-shrink-0 ${
          pack.installed
            ? 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 cursor-not-allowed'
            : 'bg-gray-600 dark:bg-gray-700 text-white hover:bg-gray-700 dark:hover:bg-gray-600'
        } disabled:opacity-50`}
      >
        {pack.installed ? t('installed') : installing ? t('installing') : t('installPack')}
      </button>
    </Card>
  );
}
