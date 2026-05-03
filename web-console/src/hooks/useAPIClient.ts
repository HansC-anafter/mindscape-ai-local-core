import { useExecutionContext } from '@/contexts/ExecutionContextContext';
import { MindscapeAPIClient } from '@/api/client';
import { useMemo } from 'react';

export function useAPIClient(): MindscapeAPIClient {
  const context = useExecutionContext();

  return useMemo(() => {
    return new MindscapeAPIClient(context);
  }, [context]);
}
