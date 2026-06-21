import React from 'react';

import { t } from '../../../../../lib/i18n';
import type { SocialMediaConnection } from './types';

interface ConnectionStatusSectionProps {
  connection: SocialMediaConnection | null;
  connecting: boolean;
  isConnected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

export function ConnectionStatusSection({
  connection,
  connecting,
  isConnected,
  onConnect,
  onDisconnect,
}: ConnectionStatusSectionProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-1">
            {t('connectionStatus' as any)}
          </h3>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 text-sm ${
                isConnected
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {isConnected ? t('socialMediaConnected' as any) : t('socialMediaNotConnected' as any)}
            </span>
          </div>
        </div>
        <div>
          {isConnected ? (
            <button
              onClick={onDisconnect}
              className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 border border-red-300 dark:border-red-700 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              {t('disconnectSocialMedia' as any)}
            </button>
          ) : (
            <button
              onClick={onConnect}
              disabled={connecting}
              className="px-4 py-2 text-sm font-medium text-white bg-gray-600 dark:bg-gray-500 rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              {connecting ? t('socialMediaConnecting' as any) : t('connectSocialMedia' as any)}
            </button>
          )}
        </div>
      </div>

      {isConnected && connection && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 gap-4 text-sm mb-4">
            <div>
              <span className="text-gray-500 dark:text-gray-400">{t('connectionName' as any)}:</span>
              <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.name}</span>
            </div>
            {connection.last_validated_at && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">{t('lastValidated' as any)}:</span>
                <span className="ml-2 text-gray-900 dark:text-gray-100">
                  {new Date(connection.last_validated_at).toLocaleString()}
                </span>
              </div>
            )}
            {connection.connection_type === 'remote' && (
              <>
                {connection.remote_cluster_url && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Remote Cluster:</span>
                    <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.remote_cluster_url}</span>
                  </div>
                )}
                {connection.remote_connection_id && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Remote Connection ID:</span>
                    <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.remote_connection_id}</span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
