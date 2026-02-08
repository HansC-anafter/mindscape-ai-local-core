'use client';

// Re-export from web-console via path alias to avoid brittle relative paths.
export {
  WorkspaceDataProvider,
  useWorkspaceData,
  useWorkspaceDataOptional
} from '@/contexts/WorkspaceDataContext';
