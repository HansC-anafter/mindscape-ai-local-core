import { getApiBaseUrl } from '@/lib/api-url';
import type {
    ChooseDirectoryResult,
    DeviceNodeStatus,
    DirectoryEntry,
    FileTypeConfig,
    NotesFolder,
} from './types';

const API_BASE = getApiBaseUrl();

export async function fetchDeviceNodeStatus(): Promise<DeviceNodeStatus> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/status`);
        if (!res.ok) throw new Error();
        return await res.json();
    } catch (err) {
        console.error('LocalContent status fetch failed:', err);
        return { connected: false, notesAvailable: false };
    }
}

export async function fetchDirectories(): Promise<DirectoryEntry[]> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/directories`);
        if (!res.ok) return getDefaultDirectories();
        return await res.json();
    } catch {
        return getDefaultDirectories();
    }
}

export async function saveDirectories(dirs: DirectoryEntry[]): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/directories`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dirs),
    });
}

export async function fetchNotesFolders(): Promise<NotesFolder[]> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/notes/folders`);
        if (!res.ok) return [];
        return await res.json();
    } catch {
        return [];
    }
}

export async function saveNotesFolders(folders: NotesFolder[]): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/notes/folders`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folders),
    });
}

export async function fetchFileTypes(): Promise<FileTypeConfig> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/file-types`);
        if (!res.ok) return getDefaultFileTypes();
        return await res.json();
    } catch {
        return getDefaultFileTypes();
    }
}

export async function saveFileTypes(config: Partial<Pick<FileTypeConfig, 'allowed_extensions' | 'blocked_extensions'>>): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/file-types`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
    });
}

export async function chooseLocalContentDirectory(): Promise<ChooseDirectoryResult> {
    const response = await fetch('/api/v1/system-settings/local-content/choose-directory', {
        method: 'POST',
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '' }));
        if (response.status === 400) {
            return { kind: 'cancelled' };
        }
        return {
            kind: 'error',
            status: response.status,
            detail: typeof err.detail === 'string' ? err.detail : '',
        };
    }

    const data = await response.json();
    if (!data.path) {
        return { kind: 'cancelled' };
    }

    return { kind: 'selected', path: data.path };
}

function getDefaultDirectories(): DirectoryEntry[] {
    return [
        { path: '~/Documents', enabled: false },
        { path: '~/Projects', enabled: false },
        { path: '~/Desktop', enabled: false },
    ];
}

function getDefaultFileTypes(): FileTypeConfig {
    return { allowed_extensions: [], blocked_extensions: [], source: 'default' };
}
