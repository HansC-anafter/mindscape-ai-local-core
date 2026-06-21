interface PathConfirmationDialogProps {
    open: boolean;
    selectedDirName: string;
    pathInputValue: string;
    dirError: string | null;
    onPathInputChange: (value: string) => void;
    onConfirm: () => void;
    onCancel: () => void;
}

export function PathConfirmationDialog({
    open,
    selectedDirName,
    pathInputValue,
    dirError,
    onPathInputChange,
    onConfirm,
    onCancel,
}: PathConfirmationDialogProps) {
    if (!open) {
        return null;
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md overflow-hidden border border-gray-100 dark:border-gray-700">
                <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">確認目錄路徑</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        瀏覽器無法直接取得完整絕對路徑，我們已根據您的選擇預測此路徑。請確認或修改為正確的完整路徑。
                    </p>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            選擇的資料夾名稱
                        </label>
                        <div className="px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-600 dark:text-gray-400 font-mono">
                            {selectedDirName}
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            完整絕對路徑 <span className="text-red-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={pathInputValue}
                            onChange={(event) => onPathInputChange(event.target.value)}
                            className={`w-full px-3 py-2 bg-white dark:bg-gray-900 border ${dirError ? 'border-red-300 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500 focus:border-blue-500'} rounded-lg shadow-sm text-sm text-gray-900 dark:text-gray-100 font-mono`}
                            placeholder="/Users/username/path/to/folder"
                            autoFocus
                            onKeyDown={(event) => {
                                if (event.key === 'Enter') onConfirm();
                                if (event.key === 'Escape') onCancel();
                            }}
                        />
                        {dirError && (
                            <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">{dirError}</p>
                        )}
                    </div>
                </div>
                <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50 flex justify-end gap-3">
                    <button
                        onClick={onCancel}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                    >
                        取消
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={!pathInputValue.trim()}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm"
                    >
                        確認並新增
                    </button>
                </div>
            </div>
        </div>
    );
}
