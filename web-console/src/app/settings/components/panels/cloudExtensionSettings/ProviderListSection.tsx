import { t } from '../../../../../lib/i18n';
import { ProviderPacksSection } from './ProviderPacksSection';
import type { Pack, Provider, TestStatus } from './types';

interface ProviderListSectionProps {
  providers: Provider[];
  packs: Record<string, Pack[]>;
  loadingPacks: Record<string, boolean>;
  installingPacks: Record<string, boolean>;
  showPacks: Record<string, boolean>;
  testStatus: Record<string, TestStatus>;
  testMessages: Record<string, string>;
  onTestConnection: (providerId: string) => void;
  onEdit: (provider: Provider) => void;
  onDelete: (providerId: string) => void;
  onLoadPacks: (providerId: string) => void;
  onHidePacks: (providerId: string) => void;
  onInstallPacks: (providerId: string) => void;
}

export function ProviderListSection({
  providers,
  packs,
  loadingPacks,
  installingPacks,
  showPacks,
  testStatus,
  testMessages,
  onTestConnection,
  onEdit,
  onDelete,
  onLoadPacks,
  onHidePacks,
  onInstallPacks,
}: ProviderListSectionProps) {
  if (providers.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
        {t('noCloudProvidersConfigured' as any)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {providers.map((provider) => (
        <div
          key={provider.provider_id}
          className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-medium text-gray-900 dark:text-gray-100">
                  {provider.name}
                </h3>
                <span className={`px-2 py-1 text-xs rounded ${
                  provider.enabled
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                }`}>
                  {provider.enabled ? t('enabled' as any) : t('disabled' as any)}
                </span>
                <span className={`px-2 py-1 text-xs rounded ${
                  provider.configured
                    ? 'bg-accent-10 text-accent dark:bg-blue-900/20 dark:text-blue-400'
                    : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
                }`}>
                  {provider.configured ? t('configured' as any) : t('notConfigured' as any)}
                </span>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {provider.description}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                {t('providerId' as any)}: {provider.provider_id} | {t('providerType' as any)}: {provider.provider_type}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onTestConnection(provider.provider_id)}
                disabled={testStatus[provider.provider_id] === 'testing'}
                className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
              >
                {testStatus[provider.provider_id] === 'testing' ? t('testing' as any) : t('test' as any)}
              </button>
              <button
                type="button"
                onClick={() => onEdit(provider)}
                className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
              >
                {t('editProvider' as any)}
              </button>
              <button
                type="button"
                onClick={() => onDelete(provider.provider_id)}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700"
              >
                {t('deleteProvider' as any)}
              </button>
            </div>
          </div>

          {testMessages[provider.provider_id] && (
            <div
              className={`text-sm ${
                testStatus[provider.provider_id] === 'success'
                  ? 'text-green-600 dark:text-green-400'
                  : testStatus[provider.provider_id] === 'error'
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-600 dark:text-gray-400'
              }`}
            >
              {testMessages[provider.provider_id]}
            </div>
          )}

          {provider.configured && (
            <ProviderPacksSection
              providerId={provider.provider_id}
              packs={packs[provider.provider_id] || []}
              visible={Boolean(showPacks[provider.provider_id])}
              loading={Boolean(loadingPacks[provider.provider_id])}
              installing={Boolean(installingPacks[provider.provider_id])}
              onLoad={() => onLoadPacks(provider.provider_id)}
              onHide={() => onHidePacks(provider.provider_id)}
              onInstall={() => onInstallPacks(provider.provider_id)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
