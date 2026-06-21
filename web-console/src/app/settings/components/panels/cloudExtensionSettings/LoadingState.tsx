import { t } from '../../../../../lib/i18n';

export function LoadingState() {
  return (
    <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
      {t('loading' as any)}
    </div>
  );
}
