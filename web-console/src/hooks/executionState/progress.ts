import type { ExecutionStep } from '@/components/execution';

export function calculateProgress(steps: ExecutionStep[]): number {
  if (steps.length === 0) return 0;

  const completed = steps.filter(step => step.status === 'completed').length;
  const inProgress = steps.find(step => step.status === 'in_progress');
  const inProgressWeight = inProgress ? 0.5 : 0;

  return Math.round(((completed + inProgressWeight) / steps.length) * 100);
}
