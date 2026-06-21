interface WorkspaceSettingsStorageSectionProps {
  hasWorkspaceStoragePath: boolean;
  storageBasePath: string;
  artifactsDir: string;
  storagePathChanged: boolean;
  saving: boolean;
  error: string | null;
  success: boolean;
  onStorageBasePathChange: (value: string) => void;
  onArtifactsDirChange: (value: string) => void;
  onOpenFolder: () => Promise<void>;
  onSaveStorageSettings: () => Promise<void>;
}

export default function WorkspaceSettingsStorageSection({
  hasWorkspaceStoragePath,
  storageBasePath,
  artifactsDir,
  storagePathChanged,
  saving,
  error,
  success,
  onStorageBasePathChange,
  onArtifactsDirChange,
  onOpenFolder,
  onSaveStorageSettings,
}: WorkspaceSettingsStorageSectionProps) {
  return (
    <>
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">Storage Settings</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Configure the workspace file storage path. All Playbook artifacts will be stored under this path.
        </p>
      </div>

      {!hasWorkspaceStoragePath && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-sm font-medium text-yellow-800">Warning: Storage path not configured</h3>
              <p className="mt-1 text-sm text-yellow-700">
                Storage path not configured for this workspace. Please set a path, or go to{' '}
                <a href="/settings" className="underline font-medium">System Settings</a>{' '}
                to enable Local File System access.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label htmlFor="storage-base-path" className="block text-sm font-medium text-gray-700 mb-1">
            Base Storage Path
          </label>
          <div className="flex items-center gap-2">
            <input
              id="storage-base-path"
              type="text"
              value={storageBasePath}
              onChange={(event) => onStorageBasePathChange(event.target.value)}
              placeholder="/path/to/storage"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {storageBasePath && (
              <button
                onClick={() => void onOpenFolder()}
                className="px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
                title="Open containing folder"
              >
                Open Folder
              </button>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            All Playbook artifacts will be stored in subdirectories under this path
          </p>
        </div>

        <div>
          <label htmlFor="artifacts-dir" className="block text-sm font-medium text-gray-700 mb-1">
            Artifacts Directory
          </label>
          <input
            id="artifacts-dir"
            type="text"
            value={artifactsDir}
            onChange={(event) => onArtifactsDirChange(event.target.value)}
            placeholder="artifacts"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Artifacts will be stored in this subdirectory under the base path (default: artifacts)
          </p>
        </div>

        {storagePathChanged && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-yellow-800">Storage Path Change Warning</h3>
                <p className="mt-1 text-sm text-yellow-700">
                  Changing storage path affects future file archiving. Existing files may not be found automatically.
                  Please confirm you understand the impact of this change.
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            </div>
          </div>
        )}

        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-green-700">Storage settings saved successfully</p>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => void onSaveStorageSettings()}
            disabled={saving || !storagePathChanged}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </>
  );
}
