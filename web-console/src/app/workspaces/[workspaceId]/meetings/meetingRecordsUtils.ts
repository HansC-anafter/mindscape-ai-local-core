export function getMeetingRecordStatusStyle(status: string): string {
    const styles: Record<string, string> = {
        active: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        planned: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
        closing: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
        closed: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
        aborted: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[status] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

export function formatWorkflowEvidenceLabel(label: string): string {
    return label.replace(/^Recent /, '').replace(/^Latest /, '');
}
