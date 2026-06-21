'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { DirectoryAccessSection } from './localContentView/DirectoryAccessSection';
import { FileTypeGovernanceSection } from './localContentView/FileTypeGovernanceSection';
import { FILE_CATEGORIES } from './localContentView/fileCategories';
import { LoadingState } from './localContentView/LoadingState';
import { LocalContentHeader } from './localContentView/LocalContentHeader';
import { NotesFolderSection } from './localContentView/NotesFolderSection';
import { PathConfirmationDialog } from './localContentView/PathConfirmationDialog';
import {
    chooseLocalContentDirectory,
    fetchDeviceNodeStatus,
    fetchDirectories,
    fetchFileTypes,
    fetchNotesFolders,
    saveDirectories,
    saveFileTypes,
    saveNotesFolders,
} from './localContentView/resourceActions';
import { SaveToast } from './localContentView/SaveToast';
import type {
    DeviceNodeStatus,
    DirectoryEntry,
    FileCategory,
    FileCategoryKind,
    FileTypeConfig,
    NotesFolder,
} from './localContentView/types';

export function LocalContentView() {
    const [status, setStatus] = useState<DeviceNodeStatus>({ connected: false, notesAvailable: false });
    const [directories, setDirectories] = useState<DirectoryEntry[]>([]);
    const [notesFolders, setNotesFolders] = useState<NotesFolder[]>([]);
    const [fileTypes, setFileTypes] = useState<FileTypeConfig>({ allowed_extensions: [], blocked_extensions: [], source: 'default' });
    const [loading, setLoading] = useState(true);
    const [newDirInput, setNewDirInput] = useState('');
    const [showAddDir, setShowAddDir] = useState(false);
    const [toast, setToast] = useState<string | null>(null);
    const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [showPathInputDialog, setShowPathInputDialog] = useState(false);
    const [selectedDirName, setSelectedDirName] = useState('');
    const [pathInputValue, setPathInputValue] = useState('');
    const [dirError, setDirError] = useState<string | null>(null);

    const showToast = (msg = '✓ 已儲存') => {
        if (toastTimer.current) clearTimeout(toastTimer.current);
        setToast(msg);
        toastTimer.current = setTimeout(() => setToast(null), 1500);
    };

    const loadAll = useCallback(async () => {
        setLoading(true);
        const [deviceStatus, directoryEntries, noteEntries, fileTypeConfig] = await Promise.all([
            fetchDeviceNodeStatus(),
            fetchDirectories(),
            fetchNotesFolders(),
            fetchFileTypes(),
        ]);
        setStatus(deviceStatus);
        setDirectories(directoryEntries);
        setNotesFolders(noteEntries);
        setFileTypes(fileTypeConfig);
        setLoading(false);
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    const clearDirectoryInput = () => {
        setShowAddDir(false);
        setNewDirInput('');
        setDirError(null);
    };

    const toggleDirectory = async (idx: number) => {
        const updated = directories.map((directory, index) => (
            index === idx ? { ...directory, enabled: !directory.enabled } : directory
        ));
        setDirectories(updated);
        await saveDirectories(updated);
        showToast();
    };

    const addDirectory = async () => {
        const trimmed = newDirInput.trim();
        if (!trimmed) return;

        if (directories.some((directory) => directory.path === trimmed)) {
            setDirError('目錄已存在');
            return;
        }

        const updated = [...directories, { path: trimmed, enabled: true }];
        setDirectories(updated);
        clearDirectoryInput();
        await saveDirectories(updated);
        showToast('✓ 已新增');
    };

    const handleDirectoryPicker = async () => {
        try {
            const result = await chooseLocalContentDirectory();
            if (result.kind === 'cancelled') {
                return;
            }
            if (result.kind === 'error') {
                setDirError(result.status === 503 ? 'Device Node 未連線，請先啟動 Device Node' : result.detail || '無法開啟目錄選擇器');
                return;
            }

            const chosenPath = result.path;
            if (directories.some((directory) => directory.path === chosenPath)) {
                setDirError('目錄已存在');
                return;
            }

            const updated = [...directories, { path: chosenPath, enabled: true }];
            setDirectories(updated);
            setDirError(null);
            await saveDirectories(updated);
            await loadAll();
            showToast('✓ 已新增');
        } catch (err) {
            console.error('Directory picker error:', err);
            setDirError('無法開啟目錄選擇器，請直接輸入路徑。');
        }
    };

    const confirmPathDialog = async () => {
        const trimmed = pathInputValue.trim();
        if (!trimmed) return;

        if (directories.some((directory) => directory.path === trimmed)) {
            setDirError('目錄已存在');
            return;
        }

        const updated = [...directories, { path: trimmed, enabled: true }];
        setDirectories(updated);
        setShowPathInputDialog(false);
        setPathInputValue('');
        setDirError(null);
        await saveDirectories(updated);
        showToast('✓ 已新增');
    };

    const removeDirectory = async (idx: number) => {
        const updated = directories.filter((_, index) => index !== idx);
        setDirectories(updated);
        await saveDirectories(updated);
        showToast('✓ 已移除');
    };

    const toggleNotesFolder = async (idx: number) => {
        const updated = notesFolders.map((folder, index) => (
            index === idx ? { ...folder, enabled: !folder.enabled } : folder
        ));
        setNotesFolders(updated);
        await saveNotesFolders(updated);
        showToast();
    };

    const toggleAllNotes = async (enabled: boolean) => {
        const updated = notesFolders.map((folder) => ({ ...folder, enabled }));
        setNotesFolders(updated);
        await saveNotesFolders(updated);
        showToast();
    };

    const allowedSet = new Set(fileTypes.allowed_extensions);
    const blockedSet = new Set(fileTypes.blocked_extensions);

    const getActiveSet = (kind: FileCategoryKind) =>
        kind === 'allowed' ? allowedSet : blockedSet;

    const persistExts = async (kind: FileCategoryKind, newSet: Set<string>) => {
        const sorted = Array.from(newSet).sort();
        const update = kind === 'allowed'
            ? { allowed_extensions: sorted }
            : { blocked_extensions: sorted };
        setFileTypes((prev) => ({ ...prev, ...update }));
        await saveFileTypes(update);
        showToast();
    };

    const toggleCategory = async (category: FileCategory) => {
        const set = new Set(getActiveSet(category.kind));
        const allIn = category.extensions.every((extension) => set.has(extension));
        if (allIn) {
            category.extensions.forEach((extension) => set.delete(extension));
        } else {
            category.extensions.forEach((extension) => set.add(extension));
        }
        await persistExts(category.kind, set);
    };

    const toggleSingleExt = async (kind: FileCategoryKind, extension: string) => {
        const set = new Set(getActiveSet(kind));
        if (set.has(extension)) {
            set.delete(extension);
        } else {
            set.add(extension);
        }
        await persistExts(kind, set);
    };

    const allNotesSelected = notesFolders.length > 0 && notesFolders.every((folder) => folder.enabled);
    const someNotesSelected = notesFolders.some((folder) => folder.enabled) && !allNotesSelected;
    const enabledDirs = directories.filter((directory) => directory.enabled).length;
    const allowedCategories = FILE_CATEGORIES.filter((category) => category.kind === 'allowed');
    const blockedCategories = FILE_CATEGORIES.filter((category) => category.kind === 'blocked');
    const activeAllowedCount = allowedCategories.filter((category) => category.extensions.some((extension) => allowedSet.has(extension))).length;
    const activeBlockedCount = blockedCategories.filter((category) => category.extensions.some((extension) => blockedSet.has(extension))).length;

    if (loading) {
        return <LoadingState />;
    }

    return (
        <>
            <div className="h-full overflow-y-auto bg-gray-50 dark:bg-gray-800">
                <LocalContentHeader status={status} />
                <div className="p-6">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div className="space-y-6">
                            <DirectoryAccessSection
                                directories={directories}
                                enabledCount={enabledDirs}
                                dirError={dirError}
                                showAddDir={showAddDir}
                                newDirInput={newDirInput}
                                onAddDirectory={addDirectory}
                                onChooseDirectory={handleDirectoryPicker}
                                onNewDirectoryChange={(value) => {
                                    setNewDirInput(value);
                                    if (dirError) setDirError(null);
                                }}
                                onCancelAddDirectory={clearDirectoryInput}
                                onShowAddDirectory={() => setShowAddDir(true)}
                                onRemoveDirectory={removeDirectory}
                                onToggleDirectory={toggleDirectory}
                            />
                            <NotesFolderSection
                                status={status}
                                notesFolders={notesFolders}
                                allNotesSelected={allNotesSelected}
                                someNotesSelected={someNotesSelected}
                                onToggleAllNotes={toggleAllNotes}
                                onToggleNotesFolder={toggleNotesFolder}
                            />
                        </div>
                        <FileTypeGovernanceSection
                            allowedCategories={allowedCategories}
                            blockedCategories={blockedCategories}
                            allowedSet={allowedSet}
                            blockedSet={blockedSet}
                            activeAllowedCount={activeAllowedCount}
                            activeBlockedCount={activeBlockedCount}
                            onToggleCategory={toggleCategory}
                            onToggleSingleExt={toggleSingleExt}
                        />
                    </div>
                </div>
            </div>

            <PathConfirmationDialog
                open={showPathInputDialog}
                selectedDirName={selectedDirName}
                pathInputValue={pathInputValue}
                dirError={dirError}
                onPathInputChange={(value) => {
                    setPathInputValue(value);
                    if (dirError) setDirError(null);
                }}
                onConfirm={confirmPathDialog}
                onCancel={() => {
                    setShowPathInputDialog(false);
                    setDirError(null);
                }}
            />
            <SaveToast message={toast} />
        </>
    );
}
