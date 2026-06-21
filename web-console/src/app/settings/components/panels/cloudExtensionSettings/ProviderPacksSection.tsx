import { t } from '../../../../../lib/i18n';
import type { Pack } from './types';

interface ProviderPacksSectionProps {
  providerId: string;
  packs: Pack[];
  visible: boolean;
  loading: boolean;
  installing: boolean;
  onLoad: () => void;
  onHide: () => void;
  onInstall: () => void;
}

export function ProviderPacksSection({
  providerId,
  packs,
  visible,
  loading,
  installing,
  onLoad,
  onHide,
  onInstall,
}: ProviderPacksSectionProps) {
  return (
    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
          Available Packs
        </h4>
        {!visible ? (
          <button
            type="button"
            onClick={onLoad}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'View Packs'}
          </button>
        ) : (
          <button
            type="button"
            onClick={onHide}
            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700"
          >
            Hide Packs
          </button>
        )}
      </div>

      {visible && (
        <div className="space-y-2" data-provider-id={providerId}>
          {loading ? (
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
              {t('loading' as any) || 'Loading...'}
            </div>
          ) : packs.length > 0 ? (
            <>
              {packs.map((pack) => (
                <div
                  key={pack.pack_ref}
                  className={`p-3 rounded border ${
                    pack.installed
                      ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                      : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h5 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {pack.display_name}
                        </h5>
                        {pack.installed && (
                          <span className="px-2 py-0.5 text-xs rounded bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                            {t('installed' as any) || 'Installed'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        {pack.description}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                        Version: {pack.version} | Size: {pack.size ? `${(pack.size / 1024).toFixed(1)} KB` : 'N/A'}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={onInstall}
                  disabled={installing}
                  className="w-full px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
                >
                  {installing ? 'Installing...' : 'Install All Packs'}
                </button>
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
              No packs available
            </div>
          )}
        </div>
      )}
    </div>
  );
}
