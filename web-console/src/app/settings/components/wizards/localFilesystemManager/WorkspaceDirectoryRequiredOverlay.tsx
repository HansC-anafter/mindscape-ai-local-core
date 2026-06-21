'use client';

interface WorkspaceDirectoryRequiredOverlayProps {
  error: string | null;
  hasSelectedPath: boolean;
  onBrowseDirectory: () => void | Promise<void>;
  workspaceMode: boolean;
}

export function WorkspaceDirectoryRequiredOverlay({
  error,
  hasSelectedPath,
  onBrowseDirectory,
  workspaceMode,
}: WorkspaceDirectoryRequiredOverlayProps) {
  if (!workspaceMode || hasSelectedPath) {
    return null;
  }

  const directoryPickerAvailable = typeof window !== 'undefined' && 'showDirectoryPicker' in window;

  return (
    <div className="absolute inset-0 bg-white dark:bg-gray-800 bg-opacity-95 dark:bg-opacity-95 rounded-lg z-10 flex flex-col items-center justify-center p-8">
      <div className="text-center max-w-md w-full">
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}
        <div className="mb-6">
          <h3 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Select Project Root Directory</h3>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            Please use the button below to select your project root directory. The system will automatically fill in the complete path.
          </p>
        </div>
        <button
          type="button"
          onClick={onBrowseDirectory}
          className="px-8 py-4 bg-accent dark:bg-blue-700 hover:bg-accent/90 dark:hover:bg-blue-600 text-white rounded-lg text-lg font-medium flex items-center space-x-3 shadow-lg transition-colors mx-auto"
          title={
            directoryPickerAvailable
              ? 'Open system directory picker (Chrome/Edge)'
              : 'Not available in this browser. Use quick select or manual input.'
          }
        >
          <span>Browse Directory {directoryPickerAvailable ? '(Chrome/Edge)' : '(Not Available)'}</span>
        </button>
        <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          {directoryPickerAvailable
            ? 'Click this button to open the system directory picker and select your project root directory'
            : 'Directory picker is not available in this browser. Please use manual input below'}
        </p>
      </div>
    </div>
  );
}
