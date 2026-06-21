import type { ThreadBundle } from '@/hooks/useThreadBundle';

export type BundleSection = 'overview' | 'deliverables' | 'references' | 'runs' | 'sources';

export interface ThreadBundlePanelProps {
  threadId: string | null;
  workspaceId: string;
  isOpen: boolean;
  onClose: () => void;
  apiUrl?: string;
  embedded?: boolean;
}

export type ThreadReferenceSourceType = ThreadBundle['references'][number]['source_type'];

export interface ThreadReferenceSourceOption {
  value: ThreadReferenceSourceType;
  label: string;
}

export interface AddThreadReferenceParams {
  apiUrl: string;
  workspaceId: string;
  threadId: string;
  sourceType: ThreadReferenceSourceType;
  uri: string;
  title: string;
  snippet: string;
  reason: string;
}
