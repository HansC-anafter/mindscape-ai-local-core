import { CollapsibleSection } from './CollapsibleSection';
import type { DeviceNodeStatus, NotesFolder } from './types';

interface NotesFolderSectionProps {
    status: DeviceNodeStatus;
    notesFolders: NotesFolder[];
    allNotesSelected: boolean;
    someNotesSelected: boolean;
    onToggleAllNotes: (enabled: boolean) => void;
    onToggleNotesFolder: (index: number) => void;
}

export function NotesFolderSection({
    status,
    notesFolders,
    allNotesSelected,
    someNotesSelected,
    onToggleAllNotes,
    onToggleNotesFolder,
}: NotesFolderSectionProps) {
    return (
        <CollapsibleSection
            icon="📝"
            title="記事本 (Apple Notes)"
            description="選擇要授權存取的 Apple Notes 資料夾"
            badge={
                notesFolders.length > 0 ? (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                        {notesFolders.filter((folder) => folder.enabled).length}/{notesFolders.length}
                    </span>
                ) : undefined
            }
        >
            {!status.notesAvailable ? (
                <div className="px-5 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
                    {!status.connected
                        ? 'Device Node 未連線，無法取得 Notes 資料夾'
                        : '需要在 macOS 系統設定中授權 Notes 存取權限'}
                </div>
            ) : (
                <>
                    <div className="px-5 py-2.5 border-b border-gray-100 dark:border-gray-800 flex items-center">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={allNotesSelected}
                                ref={(el) => { if (el) el.indeterminate = someNotesSelected; }}
                                onChange={() => onToggleAllNotes(!allNotesSelected)}
                                className="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 accent-green-600"
                            />
                            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                                {allNotesSelected ? '取消全選' : '全選'}
                            </span>
                        </label>
                    </div>
                    <div className="divide-y divide-gray-100 dark:divide-gray-800">
                        {notesFolders.map((folder, idx) => (
                            <div
                                key={`${folder.name}-${idx}`}
                                className="flex items-center px-5 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer"
                                onClick={() => onToggleNotesFolder(idx)}
                            >
                                <input
                                    type="checkbox"
                                    checked={folder.enabled}
                                    onChange={() => onToggleNotesFolder(idx)}
                                    onClick={(event) => event.stopPropagation()}
                                    className="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 accent-green-600 mr-3"
                                />
                                <span className="text-gray-400 dark:text-gray-500 mr-2 text-sm">📒</span>
                                <span className="text-sm text-gray-800 dark:text-gray-200">{folder.name}</span>
                            </div>
                        ))}
                    </div>
                </>
            )}
        </CollapsibleSection>
    );
}
