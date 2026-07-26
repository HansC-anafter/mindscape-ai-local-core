import type { Dispatch, SetStateAction } from 'react';
import { useT } from '../../../../../lib/i18n';
import type { CloudProviderFormData, Provider } from './types';

interface ProviderFormSectionProps {
  formData: CloudProviderFormData;
  saving: boolean;
  editingProvider: Provider | null;
  onFormDataChange: Dispatch<SetStateAction<CloudProviderFormData>>;
  onCancel: () => void;
  onSave: () => void;
}

export function ProviderFormSection({
  formData,
  saving,
  editingProvider,
  onFormDataChange,
  onCancel,
  onSave,
}: ProviderFormSectionProps) {
  const t = useT();
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
      <h3 className="font-medium text-gray-900 dark:text-gray-100">
        {editingProvider ? t('editProvider' as any) : t('addProvider' as any)}
      </h3>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('providerId' as any)} <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={formData.provider_id}
          onChange={(event) => onFormDataChange({ ...formData, provider_id: event.target.value })}
          placeholder={t('enterProviderId' as any)}
          disabled={Boolean(editingProvider)}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('providerType' as any)} <span className="text-red-500">*</span>
        </label>
        <select
          value={formData.provider_type}
          onChange={(event) => onFormDataChange({
            ...formData,
            provider_type: event.target.value as CloudProviderFormData['provider_type'],
          })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        >
          <option value="official">{t('providerTypeOfficial' as any)}</option>
          <option value="generic_http">{t('providerTypeGenericHttp' as any)}</option>
        </select>
      </div>

      {formData.provider_type === 'official' && (
        <>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('apiUrl' as any)} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.config.api_url}
              onChange={(event) => onFormDataChange({
                ...formData,
                config: { ...formData.config, api_url: event.target.value },
              })}
              placeholder={t('apiUrlPlaceholder' as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('licenseKey' as any)} <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={formData.config.license_key}
              onChange={(event) => onFormDataChange({
                ...formData,
                config: { ...formData.config, license_key: event.target.value },
              })}
              placeholder={t('licenseKeyPlaceholder' as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
        </>
      )}

      {formData.provider_type === 'generic_http' && (
        <>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('providerName' as any)} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.config.name}
              onChange={(event) => onFormDataChange({
                ...formData,
                config: { ...formData.config, name: event.target.value },
              })}
              placeholder={t('providerNamePlaceholder' as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('apiUrl' as any)} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.config.api_url}
              onChange={(event) => onFormDataChange({
                ...formData,
                config: { ...formData.config, api_url: event.target.value },
              })}
              placeholder={t('apiUrlPlaceholderGeneric' as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('authenticationType' as any)} <span className="text-red-500">*</span>
            </label>
            <select
              value={formData.config.auth.auth_type}
              onChange={(event) => onFormDataChange({
                ...formData,
                config: {
                  ...formData.config,
                  auth: { ...formData.config.auth, auth_type: event.target.value },
                },
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            >
              <option value="bearer">{t('bearerToken' as any)}</option>
              <option value="api_key">{t('apiKey' as any)}</option>
            </select>
          </div>
          {formData.config.auth.auth_type === 'bearer' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('token' as any)} <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={formData.config.auth.token}
                onChange={(event) => onFormDataChange({
                  ...formData,
                  config: {
                    ...formData.config,
                    auth: { ...formData.config.auth, token: event.target.value },
                  },
                })}
                placeholder={t('tokenPlaceholder' as any)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          )}
          {formData.config.auth.auth_type === 'api_key' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('apiKey' as any)} <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={formData.config.auth.api_key}
                onChange={(event) => onFormDataChange({
                  ...formData,
                  config: {
                    ...formData.config,
                    auth: { ...formData.config.auth, api_key: event.target.value },
                  },
                })}
                placeholder={t('apiKeyPlaceholder' as any)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          )}
        </>
      )}

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="enabled"
          checked={formData.enabled}
          onChange={(event) => onFormDataChange({ ...formData, enabled: event.target.checked })}
          className="w-4 h-4 text-gray-600 bg-gray-100 border-gray-300 rounded focus:ring-gray-500"
        />
        <label htmlFor="enabled" className="text-sm text-gray-700 dark:text-gray-300">
          {t('enableThisProvider' as any)}
        </label>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
        >
          {t('cancel' as any)}
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving || !formData.provider_id || !formData.config.api_url}
          className="px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
        >
          {saving ? t('saving' as any) : editingProvider ? t('update' as any) : t('create' as any)}
        </button>
      </div>
    </div>
  );
}
