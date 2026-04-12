export function getPerformanceColor(level: string): string {
  switch (level) {
    case 'high':
      return 'text-green-600 dark:text-green-400';
    case 'medium':
      return 'text-yellow-600 dark:text-yellow-400';
    case 'low':
      return 'text-red-600 dark:text-red-400';
    default:
      return 'text-gray-600 dark:text-gray-400';
  }
}

export function getPerformanceBgColor(level: string): string {
  switch (level) {
    case 'high':
      return 'bg-green-100 dark:bg-green-900/20';
    case 'medium':
      return 'bg-yellow-100 dark:bg-yellow-900/20';
    case 'low':
      return 'bg-red-100 dark:bg-red-900/20';
    default:
      return 'bg-gray-100 dark:bg-gray-700';
  }
}

