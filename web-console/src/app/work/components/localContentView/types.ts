export interface DirectoryEntry {
    path: string;
    enabled: boolean;
    host_path?: string | null;
}

export interface NotesFolder {
    name: string;
    enabled: boolean;
}

export interface DeviceNodeStatus {
    connected: boolean;
    notesAvailable: boolean;
}

export interface FileTypeConfig {
    allowed_extensions: string[];
    blocked_extensions: string[];
    source: string;
}

export type FileCategoryKind = 'allowed' | 'blocked';

export interface FileCategory {
    id: string;
    label: string;
    icon: string;
    extensions: string[];
    kind: FileCategoryKind;
}

export type ChooseDirectoryResult =
    | { kind: 'selected'; path: string }
    | { kind: 'cancelled' }
    | { kind: 'error'; status: number; detail: string };
