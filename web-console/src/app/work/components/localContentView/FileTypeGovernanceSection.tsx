import { CategoryCard } from './CategoryCard';
import { CollapsibleSection } from './CollapsibleSection';
import type { FileCategory, FileCategoryKind } from './types';

interface FileTypeGovernanceSectionProps {
    allowedCategories: FileCategory[];
    blockedCategories: FileCategory[];
    allowedSet: Set<string>;
    blockedSet: Set<string>;
    activeAllowedCount: number;
    activeBlockedCount: number;
    onToggleCategory: (category: FileCategory) => void;
    onToggleSingleExt: (kind: FileCategoryKind, extension: string) => void;
}

export function FileTypeGovernanceSection({
    allowedCategories,
    blockedCategories,
    allowedSet,
    blockedSet,
    activeAllowedCount,
    activeBlockedCount,
    onToggleCategory,
    onToggleSingleExt,
}: FileTypeGovernanceSectionProps) {
    return (
        <div className="space-y-6">
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
                    {allowedCategories.map((category) => (
                        <CategoryCard
                            key={category.id}
                            category={category}
                            activeExts={allowedSet}
                            onToggleAll={() => onToggleCategory(category)}
                            onToggleExt={(extension) => onToggleSingleExt('allowed', extension)}
                        />
                    ))}
                </div>
            </CollapsibleSection>

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
                    {blockedCategories.map((category) => (
                        <CategoryCard
                            key={category.id}
                            category={category}
                            activeExts={blockedSet}
                            locked={true}
                            onToggleAll={() => onToggleCategory(category)}
                            onToggleExt={(extension) => onToggleSingleExt('blocked', extension)}
                        />
                    ))}
                </div>
            </CollapsibleSection>
        </div>
    );
}
