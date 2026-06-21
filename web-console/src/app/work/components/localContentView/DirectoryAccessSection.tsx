import { CollapsibleSection } from './CollapsibleSection';
import type { DirectoryEntry } from './types';

interface DirectoryAccessSectionProps {
    directories: DirectoryEntry[];
    enabledCount: number;
    dirError: string | null;
    showAddDir: boolean;
    newDirInput: string;
    onAddDirectory: () => void;
    onChooseDirectory: () => void;
    onNewDirectoryChange: (value: string) => void;
    onCancelAddDirectory: () => void;
    onShowAddDirectory: () => void;
    onRemoveDirectory: (index: number) => void;
    onToggleDirectory: (index: number) => void;
}

export function DirectoryAccessSection({
    directories,
    enabledCount,
    dirError,
    showAddDir,
    newDirInput,
    onAddDirectory,
    onChooseDirectory,
    onNewDirectoryChange,
    onCancelAddDirectory,
    onShowAddDirectory,
    onRemoveDirectory,
    onToggleDirectory,
}: DirectoryAccessSectionProps) {
    return (
        <CollapsibleSection
            icon="📁"
            title="檔案目錄"
            description="授權 Device Node 存取的本機目錄"
            badge={
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                    {enabledCount}/{directories.length}
                </span>
            }
        >
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {directories.map((dir, idx) => (
                    <div key={dir.path} className="flex items-center px-5 py-3 group hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        <span className="text-gray-400 dark:text-gray-500 mr-3 text-sm">📂</span>
                        <div className="flex-1 min-w-0">
                            <span className="text-sm font-mono text-gray-800 dark:text-gray-200 truncate block">{dir.path}</span>
                            {dir.host_path && (
                                <span className="text-xs text-gray-400 dark:text-gray-500 truncate block mt-0.5">
                                    📍 {dir.host_path}
                                </span>
                            )}
                        </div>
                        <button
                            onClick={() => onRemoveDirectory(idx)}
                            className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 text-xs mr-3 transition-opacity"
                        >
                            ✕
                        </button>
                        <button
                            onClick={() => onToggleDirectory(idx)}
                            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${dir.enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}`}
                        >
                            <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${dir.enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
                        </button>
                    </div>
                ))}
            </div>
            <div className="px-5 py-3 border-t border-gray-100 dark:border-gray-800">
                {dirError && (
                    <div className="mb-2 text-xs text-red-600 dark:text-red-400">
                        {dirError}
                    </div>
                )}
                {showAddDir ? (
                    <div className="flex items-center gap-2">
                        <button
                            onClick={onChooseDirectory}
                            className="flex-shrink-0 p-1.5 border border-gray-300 dark:border-gray-600 rounded bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300"
                            title="使用系統對話框選擇目錄"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                        </button>
                        <input
                            type="text"
                            value={newDirInput}
                            onChange={(event) => onNewDirectoryChange(event.target.value)}
                            placeholder="輸入或貼上目錄路徑..."
                            className="flex-1 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono"
                            onKeyDown={(event) => {
                                if (event.key === 'Enter') onAddDirectory();
                                if (event.key === 'Escape') onCancelAddDirectory();
                            }}
                            autoFocus
                        />
                        <button onClick={onAddDirectory} className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 font-medium">新增</button>
                        <button onClick={onCancelAddDirectory} className="px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 font-medium">取消</button>
                    </div>
                ) : (
                    <div className="flex items-center gap-3">
                        <button onClick={onShowAddDirectory} className="text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 px-3 py-1.5 rounded transition-colors">
                            ✏️ 手動輸入
                        </button>
                        <button onClick={onChooseDirectory} className="text-xs text-blue-600 hover:text-blue-800 font-medium bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/30 dark:hover:bg-blue-900/50 px-3 py-1.5 rounded transition-colors flex items-center gap-1.5">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                            選擇目錄
                        </button>
                    </div>
                )}
            </div>
        </CollapsibleSection>
    );
}
