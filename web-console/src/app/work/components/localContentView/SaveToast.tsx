interface SaveToastProps {
    message: string | null;
}

export function SaveToast({ message }: SaveToastProps) {
    if (!message) {
        return null;
    }

    return (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-sm font-medium shadow-lg">
                <span>{message}</span>
            </div>
        </div>
    );
}
