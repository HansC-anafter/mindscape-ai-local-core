import { useState, type ReactNode } from 'react';

interface CollapsibleSectionProps {
    title: string;
    icon: string;
    description: string;
    defaultOpen?: boolean;
    badge?: ReactNode;
    children: ReactNode;
}

export function CollapsibleSection({
    title,
    icon,
    description,
    defaultOpen = true,
    badge,
    children,
}: CollapsibleSectionProps) {
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
