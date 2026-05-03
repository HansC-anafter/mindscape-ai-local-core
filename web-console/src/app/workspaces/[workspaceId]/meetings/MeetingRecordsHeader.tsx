'use client';

interface MeetingRecordsHeaderProps {
    onBack: () => void;
}

export function MeetingRecordsHeader({ onBack }: MeetingRecordsHeaderProps) {
    return (
        <div className="px-6 py-4 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex items-center justify-between">
            <div>
                <h1 className="text-2xl font-bold text-primary dark:text-gray-100">
                    Meeting Records
                </h1>
                <p className="text-sm text-secondary dark:text-gray-400 mt-1">
                    Session history, decisions, and action items
                </p>
            </div>
            <button
                onClick={onBack}
                className="px-3 py-1.5 text-sm text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 border border-default dark:border-gray-600 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
            >
                ← Back
            </button>
        </div>
    );
}
