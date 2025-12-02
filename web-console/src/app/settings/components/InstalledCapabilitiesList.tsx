'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { settingsApi } from '../utils/settingsApi';
import { Card } from './Card';

interface InstalledCapability {
  id?: string;
  code?: string;
  display_name?: string;
  version?: string;
  description?: string;
  scope?: string;
}

interface InstalledCapabilitiesListProps {
  refreshTrigger?: number;
}

export function InstalledCapabilitiesList({ refreshTrigger }: InstalledCapabilitiesListProps = {}) {
  const [installed, setInstalled] = useState<InstalledCapability[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInstalledCapabilities();
  }, [refreshTrigger]);

  const loadInstalledCapabilities = async () => {
    try {
      const data = await settingsApi.get<InstalledCapability[]>(
        '/api/v1/capability-packs/installed-capabilities',
        { silent: true }
      );
      setInstalled(data);
    } catch (err) {
      // 404 is expected if endpoint doesn't exist or no capabilities installed
      // Silently return empty array
      setInstalled([]);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-gray-600">{t('loading')}</div>;
  }

  if (installed.length === 0) {
    return (
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <p className="text-sm text-gray-600">{t('noCapabilityPacksInstalled')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900">{t('installedCapabilityPacks')}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {installed.map((cap) => (
          <Card key={cap.id || cap.code}>
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="font-semibold text-gray-900">{cap.display_name || cap.code}</h4>
                <p className="text-xs text-gray-500 mt-1">
                  {cap.id || cap.code} v{cap.version}
                </p>
              </div>
              {cap.scope === 'system' && (
                <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                  Official
                </span>
              )}
            </div>
            {cap.description && (
              <p className="text-sm text-gray-600 mt-2">{cap.description}</p>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
