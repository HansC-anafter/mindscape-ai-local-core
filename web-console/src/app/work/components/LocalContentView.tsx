'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DirectoryEntry {
    path: string;
    enabled: boolean;
}

interface NotesFolder {
    name: string;
    enabled: boolean;
}

interface DeviceNodeStatus {
    connected: boolean;
    notesAvailable: boolean;
}

interface FileTypeConfig {
    allowed_extensions: string[];
    blocked_extensions: string[];
    source: string;
}

// ---------------------------------------------------------------------------
// File type categories
// ---------------------------------------------------------------------------

interface FileCategory {
    id: string;
    label: string;
    icon: string;
    extensions: string[];
    kind: 'allowed' | 'blocked';
}

const FILE_CATEGORIES: FileCategory[] = [
    // ── Allowed categories ──
    {
        id: 'code',
        label: '程式碼',
        icon: '💻',
        kind: 'allowed',
        extensions: ['.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte', '.rs', '.go', '.java', '.rb', '.php', '.swift', '.kt', '.c', '.cpp', '.h', '.hpp', '.cs'],
    },
    {
        id: 'text',
        label: '文件文字',
        icon: '📄',
        kind: 'allowed',
        extensions: ['.txt', '.md', '.rst', '.org', '.rtf', '.log'],
    },
    {
        id: 'config',
        label: '設定檔',
        icon: '⚙️',
        kind: 'allowed',
        extensions: ['.json', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.env', '.editorconfig', '.gitignore', '.dockerignore'],
    },
    {
        id: 'web',
        label: '網頁前端',
        icon: '🌐',
        kind: 'allowed',
        extensions: ['.html', '.css', '.scss', '.less', '.svg'],
    },
    {
        id: 'data',
        label: '資料格式',
        icon: '📊',
        kind: 'allowed',
        extensions: ['.csv', '.tsv', '.xml', '.sql'],
    },
    {
        id: 'shell-config',
        label: 'Shell 設定',
        icon: '🐚',
        kind: 'allowed',
        extensions: ['.zshrc', '.bashrc', '.bash_profile'],
    },
    // ── Blocked categories ──
    {
        id: 'executables',
        label: '可執行檔',
        icon: '🚫',
        kind: 'blocked',
        extensions: ['.exe', '.app', '.com', '.scr'],
    },
    {
        id: 'scripts',
        label: '腳本檔案',
        icon: '⚠️',
        kind: 'blocked',
        extensions: ['.sh', '.bat', '.cmd', '.vbs', '.ps1', '.wsf'],
    },
    {
        id: 'installers',
        label: '安裝封裝',
        icon: '📦',
        kind: 'blocked',
        extensions: ['.msi', '.dmg', '.pkg', '.deb', '.rpm', '.snap'],
    },
    {
        id: 'binaries',
        label: '二進位程式庫',
        icon: '🔩',
        kind: 'blocked',
        extensions: ['.dll', '.so', '.dylib', '.bin', '.o', '.a'],
    },
    {
        id: 'disk-images',
        label: '磁碟映像',
        icon: '💿',
        kind: 'blocked',
        extensions: ['.iso', '.img'],
    },
    {
        id: 'jar-war',
        label: 'Java 封裝',
        icon: '☕',
        kind: 'blocked',
        extensions: ['.jar', '.war'],
    },
];

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const API_BASE = typeof window === 'undefined'
    ? process.env.BACKEND_URL || 'http://backend:8200'
    : process.env.NEXT_PUBLIC_API_URL || '';

async function fetchDeviceNodeStatus(): Promise<DeviceNodeStatus> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/status`);
        if (!res.ok) throw new Error();
        return await res.json();
    } catch (err) {
        console.error("LocalContent status fetch failed:", err);
        return { connected: false, notesAvailable: false };
    }
}

async function fetchDirectories(): Promise<DirectoryEntry[]> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/directories`);
        if (!res.ok) return getDefaultDirectories();
        return await res.json();
    } catch {
        return getDefaultDirectories();
    }
}

async function saveDirectories(dirs: DirectoryEntry[]): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/directories`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dirs),
    });
}

async function fetchNotesFolders(): Promise<NotesFolder[]> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/notes/folders`);
        if (!res.ok) return [];
        return await res.json();
    } catch {
        return [];
    }
}

async function saveNotesFolders(folders: NotesFolder[]): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/notes/folders`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folders),
    });
}

async function fetchFileTypes(): Promise<FileTypeConfig> {
    try {
        const res = await fetch(`${API_BASE}/api/v1/system-settings/local-content/file-types`);
        if (!res.ok) return { allowed_extensions: [], blocked_extensions: [], source: 'default' };
        return await res.json();
    } catch {
        return { allowed_extensions: [], blocked_extensions: [], source: 'default' };
    }
}

async function saveFileTypes(config: { allowed_extensions?: string[]; blocked_extensions?: string[] }): Promise<void> {
    await fetch(`${API_BASE}/api/v1/system-settings/local-content/file-types`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
    });
}

function getDefaultDirectories(): DirectoryEntry[] {
    return [
        { path: '~/Documents', enabled: false },
        { path: '~/Projects', enabled: false },
        { path: '~/Desktop', enabled: false },
    ];
}

// ---------------------------------------------------------------------------
// Collapsible Section wrapper
// ---------------------------------------------------------------------------

function CollapsibleSection({
    title,
    icon,
    description,
    defaultOpen = true,
    badge,
    children,
}: {
    title: string;
    icon: string;
    description: string;
    defaultOpen?: boolean;
    badge?: React.ReactNode;
    children: React.ReactNode;
}) {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-3 px-5 py-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
            >
                <span className="text-lg">{icon}</span>
                <div className="flex-1 text-left">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>
                </div>
                {badge && <div className="mr-2">{badge}</div>}
                <svg
                    className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {open && (
                <div className="border-t border-gray-200 dark:border-gray-700">
                    {children}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Category Toggle Card — per-extension granularity
// ---------------------------------------------------------------------------

function CategoryCard({
    category,
    activeExts,
    locked,
    onToggleAll,
    onToggleExt,
}: {
    category: FileCategory;
    activeExts: Set<string>;
    locked?: boolean;
    onToggleAll: () => void;
    onToggleExt: (ext: string) => void;
}) {
    const isBlocked = category.kind === 'blocked';
    const total = category.extensions.length;
    const activeCount = category.extensions.filter((e) => activeExts.has(e)).length;
    const allActive = activeCount === total;
    const someActive = activeCount > 0;

    // Border/bg based on activation state
    const cardBorder = someActive
        ? isBlocked
            ? 'border-red-300 dark:border-red-700 bg-red-50/50 dark:bg-red-900/10'
            : 'border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/10'
        : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50';

    return (
        <div className={`rounded-lg border p-3 transition-all ${cardBorder}`}>
            {/* Header — click = toggle all */}
            <button
                onClick={locked ? undefined : onToggleAll}
                className={`w-full flex items-center gap-2 mb-2 ${locked ? 'cursor-not-allowed' : 'cursor-pointer'}`}
            >
                <span className="text-sm">{category.icon}</span>
                <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">{category.label}</span>
                <span className="text-[10px] text-gray-400 dark:text-gray-500">{activeCount}/{total}</span>
                {locked ? (
                    <span className="ml-auto text-xs text-gray-400">🔒</span>
                ) : (
                    <div className={`ml-auto w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${allActive
                        ? isBlocked ? 'bg-red-500 border-red-500' : 'bg-green-500 border-green-500'
                        : someActive
                            ? isBlocked ? 'bg-red-300 border-red-300' : 'bg-green-300 border-green-300'
                            : 'border-gray-400 dark:border-gray-500'
                        }`}>
                        {(allActive || someActive) && (
                            <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                {allActive
                                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                    : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 12h14" />
                                }
                            </svg>
                        )}
                    </div>
                )}
            </button>
            {/* Extension tags — each independently clickable */}
            <div className="flex flex-wrap gap-1">
                {category.extensions.map((ext) => {
                    const on = activeExts.has(ext);
                    return (
                        <button
                            key={ext}
                            onClick={locked ? undefined : () => onToggleExt(ext)}
                            className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${locked ? 'cursor-not-allowed' : 'cursor-pointer'
                                } ${on
                                    ? isBlocked
                                        ? 'bg-red-200 dark:bg-red-800/40 text-red-700 dark:text-red-300 ring-1 ring-red-300 dark:ring-red-700'
                                        : 'bg-green-200 dark:bg-green-800/40 text-green-700 dark:text-green-300 ring-1 ring-green-300 dark:ring-green-700'
                                    : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                        >
                            {ext}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

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

    // Directory Picker States
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
        const [s, d, n, ft] = await Promise.all([
            fetchDeviceNodeStatus(),
            fetchDirectories(),
            fetchNotesFolders(),
            fetchFileTypes(),
        ]);
        setStatus(s);
        setDirectories(d);
        setNotesFolders(n);
        setFileTypes(ft);
        setLoading(false);
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    // Directory toggles
    const toggleDirectory = async (idx: number) => {
        const updated = directories.map((d, i) => i === idx ? { ...d, enabled: !d.enabled } : d);
        setDirectories(updated);
        await saveDirectories(updated);
        showToast();
    };

    const addDirectory = async () => {
        if (!newDirInput.trim()) return;

        const existingPaths = directories.map(d => d.path);
        if (existingPaths.includes(newDirInput.trim())) {
            setDirError('目錄已存在');
            return;
        }

        const updated = [...directories, { path: newDirInput.trim(), enabled: true }];
        setDirectories(updated);
        setNewDirInput('');
        setShowAddDir(false);
        setDirError(null);
        await saveDirectories(updated);
        showToast('✓ 已新增');
    };

    const handleDirectoryPicker = async () => {
        if ('showDirectoryPicker' in window) {
            try {
                const dirHandle = await (window as any).showDirectoryPicker({
                    mode: 'read',
                });

                const dirName = dirHandle.name;
                const isWindows = navigator.userAgent.includes('Windows');
                let defaultPath = '';

                if (directories.length > 0 && directories[0].path.trim()) {
                    const currentPath = directories[0].path.trim();
                    const separator = isWindows ? '\\' : '/';
                    if (currentPath.endsWith(separator) || currentPath.endsWith('/') || currentPath.endsWith('\\')) {
                        defaultPath = `${currentPath}${dirName}`;
                    } else {
                        defaultPath = `${currentPath}${separator}${dirName}`;
                    }
                } else {
                    defaultPath = isWindows ? `C:\\Users\\${dirName}` : `/Users/${dirName}`;
                }

                setSelectedDirName(dirName);
                setPathInputValue(defaultPath);
                setShowPathInputDialog(true);
                setDirError(null);
            } catch (err: any) {
                if (err.name !== 'AbortError') {
                    console.error('Directory picker error:', err);
                    setDirError('無法開啟目錄選擇器，請直接輸入路徑。');
                }
            }
        } else {
            setDirError('您的瀏覽器不支援目錄選擇器，請直接輸入路徑。');
        }
    };

    const confirmPathDialog = async () => {
        const trimmed = pathInputValue.trim();
        if (!trimmed) return;

        const existingPaths = directories.map(d => d.path);
        if (existingPaths.includes(trimmed)) {
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
        const updated = directories.filter((_, i) => i !== idx);
        setDirectories(updated);
        await saveDirectories(updated);
        showToast('✓ 已移除');
    };

    // Notes folder checkboxes
    const toggleNotesFolder = async (idx: number) => {
        const updated = notesFolders.map((f, i) => i === idx ? { ...f, enabled: !f.enabled } : f);
        setNotesFolders(updated);
        await saveNotesFolders(updated);
        showToast();
    };

    const toggleAllNotes = async (enabled: boolean) => {
        const updated = notesFolders.map((f) => ({ ...f, enabled }));
        setNotesFolders(updated);
        await saveNotesFolders(updated);
        showToast();
    };

    // File type helpers — per-extension + category-level
    const allowedSet = new Set(fileTypes.allowed_extensions);
    const blockedSet = new Set(fileTypes.blocked_extensions);

    const getActiveSet = (kind: 'allowed' | 'blocked') =>
        kind === 'allowed' ? allowedSet : blockedSet;

    const persistExts = async (kind: 'allowed' | 'blocked', newSet: Set<string>) => {
        const key = kind === 'allowed' ? 'allowed_extensions' : 'blocked_extensions';
        const sorted = Array.from(newSet).sort();
        setFileTypes((prev) => ({ ...prev, [key]: sorted }));
        await saveFileTypes({ [key]: sorted });
        showToast();
    };

    const toggleCategory = async (cat: FileCategory) => {
        const set = new Set(getActiveSet(cat.kind));
        const allIn = cat.extensions.every((ext) => set.has(ext));
        if (allIn) {
            cat.extensions.forEach((ext) => set.delete(ext));
        } else {
            cat.extensions.forEach((ext) => set.add(ext));
        }
        await persistExts(cat.kind, set);
    };

    const toggleSingleExt = async (kind: 'allowed' | 'blocked', ext: string) => {
        const set = new Set(getActiveSet(kind));
        if (set.has(ext)) {
            set.delete(ext);
        } else {
            set.add(ext);
        }
        await persistExts(kind, set);
    };

    const allNotesSelected = notesFolders.length > 0 && notesFolders.every((f) => f.enabled);
    const someNotesSelected = notesFolders.some((f) => f.enabled) && !allNotesSelected;
    const enabledDirs = directories.filter((d) => d.enabled).length;
    const allowedCategories = FILE_CATEGORIES.filter((c) => c.kind === 'allowed');
    const blockedCategories = FILE_CATEGORIES.filter((c) => c.kind === 'blocked');
    const activeAllowedCount = allowedCategories.filter((c) => c.extensions.some((e) => allowedSet.has(e))).length;
    const activeBlockedCount = blockedCategories.filter((c) => c.extensions.some((e) => blockedSet.has(e))).length;

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
                <div className="flex items-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span className="text-sm">Loading...</span>
                </div>
            </div>
        );
    }

    return (
        <>
            <div className="h-full overflow-y-auto bg-gray-50 dark:bg-gray-800">
                {/* Header bar */}
                <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">本機內容存取</h1>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                管理 Device Node 可存取的檔案、記事本和檔案類型
                            </p>
                        </div>
                        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${status.connected
                            ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                            : 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                            }`}>
                            <span className={`w-2 h-2 rounded-full ${status.connected ? 'bg-green-500' : 'bg-red-500'}`} />
                            {status.connected ? 'Device Node 已連線' : 'Device Node 未連線'}
                        </div>
                    </div>
                </div>

                {/* Two-column layout */}
                <div className="p-6">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* ═══ Left Column: Data Sources ═══ */}
                        <div className="space-y-6">
                            {/* Files Section */}
                            <CollapsibleSection
                                icon="📁"
                                title="檔案目錄"
                                description="授權 Device Node 存取的本機目錄"
                                badge={
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                                        {enabledDirs}/{directories.length}
                                    </span>
                                }
                            >
                                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                                    {directories.map((dir, idx) => (
                                        <div key={dir.path} className="flex items-center px-5 py-3 group hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                            <span className="text-gray-400 dark:text-gray-500 mr-3 text-sm">📂</span>
                                            <span className="flex-1 text-sm font-mono text-gray-800 dark:text-gray-200 truncate">{dir.path}</span>
                                            <button
                                                onClick={() => removeDirectory(idx)}
                                                className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 text-xs mr-3 transition-opacity"
                                            >
                                                ✕
                                            </button>
                                            <button
                                                onClick={() => toggleDirectory(idx)}
                                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${dir.enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
                                                    }`}
                                            >
                                                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${dir.enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'
                                                    }`} />
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
                                                onClick={handleDirectoryPicker}
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
                                                onChange={(e) => {
                                                    setNewDirInput(e.target.value);
                                                    if (dirError) setDirError(null);
                                                }}
                                                placeholder="輸入或貼上目錄路徑..."
                                                className="flex-1 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono"
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') addDirectory();
                                                    if (e.key === 'Escape') { setShowAddDir(false); setNewDirInput(''); setDirError(null); }
                                                }}
                                                autoFocus
                                            />
                                            <button onClick={addDirectory} className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 font-medium">新增</button>
                                            <button onClick={() => { setShowAddDir(false); setNewDirInput(''); setDirError(null); }} className="px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 font-medium">取消</button>
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-3">
                                            <button onClick={() => setShowAddDir(true)} className="text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 px-3 py-1.5 rounded transition-colors">
                                                ✏️ 手動輸入
                                            </button>
                                            <button onClick={handleDirectoryPicker} className="text-xs text-blue-600 hover:text-blue-800 font-medium bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/30 dark:hover:bg-blue-900/50 px-3 py-1.5 rounded transition-colors flex items-center gap-1.5">
                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                                </svg>
                                                選擇目錄
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </CollapsibleSection>

                            {/* Notes Section */}
                            <CollapsibleSection
                                icon="📝"
                                title="記事本 (Apple Notes)"
                                description="選擇要授權存取的 Apple Notes 資料夾"
                                badge={
                                    notesFolders.length > 0 ? (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                                            {notesFolders.filter((f) => f.enabled).length}/{notesFolders.length}
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
                                                    onChange={() => toggleAllNotes(!allNotesSelected)}
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
                                                    key={folder.name}
                                                    className="flex items-center px-5 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer"
                                                    onClick={() => toggleNotesFolder(idx)}
                                                >
                                                    <input
                                                        type="checkbox"
                                                        checked={folder.enabled}
                                                        onChange={() => toggleNotesFolder(idx)}
                                                        onClick={(e) => e.stopPropagation()}
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
                        </div>

                        {/* ═══ Right Column: File Type Governance ═══ */}
                        <div className="space-y-6">
                            {/* Allowed categories */}
                            <CollapsibleSection
                                icon="✅"
                                title="允許的檔案類型"
                                description="點擊類別快速開關，勾選的類別 AI 可讀寫"
                                defaultOpen={true}
                                badge={
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                                        {activeAllowedCount}/{allowedCategories.length}
                                    </span>
                                }
                            >
                                <div className="p-4 grid grid-cols-2 gap-3">
                                    {allowedCategories.map((cat) => (
                                        <CategoryCard
                                            key={cat.id}
                                            category={cat}
                                            activeExts={allowedSet}
                                            onToggleAll={() => toggleCategory(cat)}
                                            onToggleExt={(ext) => toggleSingleExt('allowed', ext)}
                                        />
                                    ))}
                                </div>
                            </CollapsibleSection>

                            {/* Blocked categories */}
                            <CollapsibleSection
                                icon="🚫"
                                title="封鎖的檔案類型"
                                description="高危檔案類型，封鎖清單僅允許追加"
                                defaultOpen={false}
                                badge={
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">
                                        {activeBlockedCount}/{blockedCategories.length}
                                    </span>
                                }
                            >
                                <div className="mx-4 mt-3 px-3 py-2 rounded bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800/50">
                                    <p className="text-xs text-red-700 dark:text-red-400">
                                        ⚠️ 以下類別預設全部封鎖。你可以追加封鎖更多類別，但不可解除預設封鎖。
                                    </p>
                                </div>
                                <div className="p-4 grid grid-cols-2 gap-3">
                                    {blockedCategories.map((cat) => (
                                        <CategoryCard
                                            key={cat.id}
                                            category={cat}
                                            activeExts={blockedSet}
                                            locked={true}
                                            onToggleAll={() => toggleCategory(cat)}
                                            onToggleExt={(ext) => toggleSingleExt('blocked', ext)}
                                        />
                                    ))}
                                </div>
                            </CollapsibleSection>
                        </div>
                    </div>
                </div>
            </div>

            {/* Path Confirmation Dialog */}
            {showPathInputDialog && (
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
                                    onChange={(e) => {
                                        setPathInputValue(e.target.value);
                                        if (dirError) setDirError(null);
                                    }}
                                    className={`w-full px-3 py-2 bg-white dark:bg-gray-900 border ${dirError ? 'border-red-300 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500 focus:border-blue-500'} rounded-lg shadow-sm text-sm text-gray-900 dark:text-gray-100 font-mono`}
                                    placeholder="/Users/username/path/to/folder"
                                    autoFocus
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') confirmPathDialog();
                                        if (e.key === 'Escape') { setShowPathInputDialog(false); setDirError(null); }
                                    }}
                                />
                                {dirError && (
                                    <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">{dirError}</p>
                                )}
                            </div>
                        </div>
                        <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50 flex justify-end gap-3">
                            <button
                                onClick={() => { setShowPathInputDialog(false); setDirError(null); }}
                                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={confirmPathDialog}
                                disabled={!pathInputValue.trim()}
                                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm"
                            >
                                確認並新增
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Save toast */}
            {toast && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
                    <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-sm font-medium shadow-lg">
                        <span>{toast}</span>
                    </div>
                </div>
            )}
        </>
    );
}
