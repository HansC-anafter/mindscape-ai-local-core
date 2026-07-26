import { useT } from '../../../../../lib/i18n';
import { Card } from '../../Card';
import { ProviderFormModal } from './ProviderFormModal';
import { ProviderListSection } from './ProviderListSection';
import type {
  CloudProviderFormData,
  Pack,
  Provider,
  TestStatus,
} from './types';

interface CloudPlaybookProvidersSettingsViewProps {
  loading: boolean;
  providers: Provider[];
  packs: Record<string, Pack[]>;
  loadingPacks: Record<string, boolean>;
  installingPacks: Record<string, boolean>;
  showPacks: Record<string, boolean>;
  testStatus: Record<string, TestStatus>;
  testMessages: Record<string, string>;
  showAddForm: boolean;
  editingProvider: Provider | null;
  formData: CloudProviderFormData;
  saving: boolean;
  onTestConnection: (providerId: string) => void;
  onEdit: (provider: Provider) => void;
  onDelete: (providerId: string) => void;
  onLoadPacks: (providerId: string) => void;
  onHidePacks: (providerId: string) => void;
  onInstallPacks: (providerId: string) => void;
  onFormDataChange: (formData: CloudProviderFormData) => void;
  onResetForm: () => void;
  onSave: () => void;
  onShowAddForm: () => void;
}

export function CloudPlaybookProvidersSettingsView({
  loading,
  providers,
  packs,
  loadingPacks,
  installingPacks,
  showPacks,
  testStatus,
  testMessages,
  showAddForm,
  editingProvider,
  formData,
  saving,
  onTestConnection,
  onEdit,
  onDelete,
  onLoadPacks,
  onHidePacks,
  onInstallPacks,
  onFormDataChange,
  onResetForm,
  onSave,
  onShowAddForm,
}: CloudPlaybookProvidersSettingsViewProps) {
  const t = useT();
  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading' as any)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {t('cloudPlaybookProviders' as any)}
            </h2>
          </div>

          <div className="space-y-4">
            <ProviderListSection
              providers={providers}
              packs={packs}
              loadingPacks={loadingPacks}
              installingPacks={installingPacks}
              showPacks={showPacks}
              testStatus={testStatus}
              testMessages={testMessages}
              onTestConnection={onTestConnection}
              onEdit={onEdit}
              onDelete={onDelete}
              onLoadPacks={onLoadPacks}
              onHidePacks={onHidePacks}
              onInstallPacks={onInstallPacks}
            />
          </div>

          <ProviderFormModal
            isOpen={showAddForm}
            formData={formData}
            saving={saving}
            editingProvider={editingProvider}
            onFormDataChange={onFormDataChange}
            onCancel={onResetForm}
            onSave={onSave}
          />

          {!showAddForm && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onShowAddForm}
                className="px-4 py-2 bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 text-sm font-medium"
              >
                {t('addProvider' as any)}
              </button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
