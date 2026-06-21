import { t } from '../../../../../lib/i18n';
import { Card } from '../../Card';

interface CloudFrontendUrlSectionProps {
  value: string;
  saving: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
}

export function CloudFrontendUrlSection({
  value,
  saving,
  onChange,
  onSave,
}: CloudFrontendUrlSectionProps) {
  return (
    <Card>
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            {t('cloudFrontendUrl' as any)}
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t('cloudFrontendUrlDescription' as any)}
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('cloudFrontendUrlLabel' as any)}
          </label>
          <input
            type="text"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={t('cloudFrontendUrlPlaceholder' as any)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {saving ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      </div>
    </Card>
  );
}
