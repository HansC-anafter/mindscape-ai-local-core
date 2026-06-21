import type { FileCategory, FileCategoryKind } from './types';

interface CategoryCardProps {
    category: FileCategory;
    activeExts: Set<string>;
    locked?: boolean;
    onToggleAll: () => void;
    onToggleExt: (ext: string) => void;
}

export function CategoryCard({
    category,
    activeExts,
    locked,
    onToggleAll,
    onToggleExt,
}: CategoryCardProps) {
    const isBlocked = category.kind === 'blocked';
    const total = category.extensions.length;
    const activeCount = category.extensions.filter((extension) => activeExts.has(extension)).length;
    const allActive = activeCount === total;
    const someActive = activeCount > 0;
    const cardBorder = getCategoryCardBorder(category.kind, someActive);

    return (
        <div className={`rounded-lg border p-3 transition-all ${cardBorder}`}>
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
                    <div className={`ml-auto w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${getToggleBoxClass(isBlocked, allActive, someActive)}`}>
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
            <div className="flex flex-wrap gap-1">
                {category.extensions.map((ext) => {
                    const isActive = activeExts.has(ext);
                    return (
                        <button
                            key={ext}
                            onClick={locked ? undefined : () => onToggleExt(ext)}
                            className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${locked ? 'cursor-not-allowed' : 'cursor-pointer'} ${getExtensionClass(isBlocked, isActive)}`}
                        >
                            {ext}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

function getCategoryCardBorder(kind: FileCategoryKind, someActive: boolean) {
    if (!someActive) {
        return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50';
    }
    return kind === 'blocked'
        ? 'border-red-300 dark:border-red-700 bg-red-50/50 dark:bg-red-900/10'
        : 'border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/10';
}

function getToggleBoxClass(isBlocked: boolean, allActive: boolean, someActive: boolean) {
    if (allActive) {
        return isBlocked ? 'bg-red-500 border-red-500' : 'bg-green-500 border-green-500';
    }
    if (someActive) {
        return isBlocked ? 'bg-red-300 border-red-300' : 'bg-green-300 border-green-300';
    }
    return 'border-gray-400 dark:border-gray-500';
}

function getExtensionClass(isBlocked: boolean, isActive: boolean) {
    if (!isActive) {
        return 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-300 dark:hover:bg-gray-600';
    }
    return isBlocked
        ? 'bg-red-200 dark:bg-red-800/40 text-red-700 dark:text-red-300 ring-1 ring-red-300 dark:ring-red-700'
        : 'bg-green-200 dark:bg-green-800/40 text-green-700 dark:text-green-300 ring-1 ring-green-300 dark:ring-green-700';
}
