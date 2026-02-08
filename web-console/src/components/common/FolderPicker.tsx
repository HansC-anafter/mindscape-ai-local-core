'use client';

import React, { useState, useEffect } from 'react';
import { Folder, File, ChevronRight, ChevronLeft, Search, Check, X } from 'lucide-react';
import { t } from '../../lib/i18n';
import { settingsApi } from '../../app/settings/utils/settingsApi';
import { BaseModal } from '../BaseModal';

interface FileItem {
    name: string;
    path: string;
    is_dir: boolean;
    size?: number;
    modified_at?: number;
}

interface LsResponse {
    success: boolean;
    current_path: string;
    parent_path: string | null;
    items: FileItem[];
    error?: string;
}

interface FolderPickerProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (path: string) => void;
    initialPath?: string;
    title?: string;
}

export function FolderPicker({
    isOpen,
    onClose,
    onSelect,
    initialPath = '/',
    title = t('selectFolder' as any) || 'Select Folder'
}: FolderPickerProps) {
    const [currentPath, setCurrentPath] = useState(initialPath);
    const [items, setItems] = useState<FileItem[]>([]);
    const [parentPath, setParentPath] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');

    const loadDirectory = async (path: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await settingsApi.get<LsResponse>(`/api/v1/system-settings/files/ls?path=${encodeURIComponent(path)}`);
            if (response.success) {
                setItems(response.items);
                setCurrentPath(response.current_path);
                setParentPath(response.parent_path);
            } else {
                setError(response.error || 'Failed to list directory');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to connect to backend');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            loadDirectory(currentPath);
        }
    }, [isOpen]);

    const handleItemClick = (item: FileItem) => {
        if (item.is_dir) {
            loadDirectory(item.path);
        }
    };

    const handleBack = () => {
        if (parentPath) {
            loadDirectory(parentPath);
        }
    };

    const handleSelect = () => {
        onSelect(currentPath);
        onClose();
    };

    const filteredItems = items.filter(item =>
        item.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <BaseModal isOpen={isOpen} onClose={onClose} title={title} maxWidth="max-w-2xl">
            <div className="flex flex-col h-[500px]">
                {/* Navigation Bar */}
                <div className="flex items-center space-x-2 mb-4 p-2 bg-surface-secondary dark:bg-gray-700/50 rounded-md">
                    <button
                        onClick={handleBack}
                        disabled={!parentPath || loading}
                        className="p-1 hover:bg-surface-accent dark:hover:bg-gray-600 rounded disabled:opacity-30"
                    >
                        <ChevronLeft size={20} />
                    </button>
                    <div className="flex-1 overflow-x-auto whitespace-nowrap text-sm font-mono text-secondary dark:text-gray-300 py-1">
                        {currentPath}
                    </div>
                </div>

                {/* Search */}
                <div className="relative mb-4">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary" size={16} />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder={t('searchFolders' as any) || 'Search folders...'}
                        className="w-full pl-10 pr-4 py-2 border border-default dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                </div>

                {/* Directory List */}
                <div className="flex-1 overflow-y-auto border border-default dark:border-gray-700 rounded-md">
                    {loading ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center h-full text-red-500 p-4 text-center">
                            <X size={48} className="mb-2 opacity-20" />
                            <p className="text-sm font-medium">{error}</p>
                            <button
                                onClick={() => loadDirectory(currentPath)}
                                className="mt-4 text-xs bg-red-100 dark:bg-red-900/30 px-3 py-1 rounded-full hover:bg-red-200"
                            >
                                {t('retry' as any) || 'Retry'}
                            </button>
                        </div>
                    ) : filteredItems.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-secondary opacity-50">
                            <Folder size={48} className="mb-2" />
                            <p className="text-sm">{t('emptyDirectory' as any) || 'No folders found'}</p>
                        </div>
                    ) : (
                        <div className="divide-y divide-default dark:divide-gray-700">
                            {filteredItems.map((item) => (
                                <button
                                    key={item.path}
                                    onClick={() => handleItemClick(item)}
                                    className={`w-full flex items-center p-3 text-left hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-colors ${!item.is_dir ? 'opacity-50 cursor-default' : ''}`}
                                >
                                    <div className="mr-3 text-blue-500">
                                        {item.is_dir ? <Folder size={20} /> : <File size={20} />}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-primary dark:text-gray-100 truncate">
                                            {item.name}
                                        </p>
                                    </div>
                                    {item.is_dir && <ChevronRight size={16} className="text-secondary" />}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Footer Actions */}
                <div className="flex items-center justify-between mt-6 pt-6 border-t border-default dark:border-gray-700 flex-shrink-0">
                    <div className="text-xs text-secondary truncate max-w-[60%]">
                        {t('selected' as any) || 'Selected'}: <span className="font-mono">{currentPath}</span>
                    </div>
                    <div className="flex space-x-3">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium text-secondary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-700 rounded-md transition-colors"
                        >
                            {t('cancel' as any) || 'Cancel'}
                        </button>
                        <button
                            onClick={handleSelect}
                            disabled={loading || !!error}
                            className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Check size={16} className="mr-2" />
                            {t('confirmSelection' as any) || 'Confirm Selection'}
                        </button>
                    </div>
                </div>
            </div>
        </BaseModal>
    );
}
