/**
 * Time formatting utilities for WorkbenchExecutionPanel
 */

export {
    parseServerTimestamp as parseTimestamp,
    formatLocalDateTime,
    formatLocalTime,
    minutesAgo,
} from '@/lib/time';

// Exported relative time formatter
export function formatRelativeTime(dateInput: string | Date | null | undefined): string {
    if (!dateInput) return '';
    const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
    if (isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
    const diffInMinutes = Math.floor(diffInSeconds / 60);
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
    const diffInHours = Math.floor(diffInMinutes / 60);
    if (diffInHours < 24) return `${diffInHours}h ago`;
    const diffInDays = Math.floor(diffInHours / 24);
    return `${diffInDays}d ago`;
}

/**
 * Shorten an ID for display (first 8 chars + ellipsis)
 */
export function shortId(id: string): string {
    const s = (id || '').toString();
    if (!s) return '';
    return s.length > 8 ? `${s.slice(0, 8)}…` : s;
}
