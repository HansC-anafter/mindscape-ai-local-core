export interface IGWorkbenchProps {
  workspaceId: string;
  apiUrl?: string;
}

export type WorkbenchModuleType =
  | 'access'
  | 'discovery'
  | 'managed'
  | 'plan'
  | 'produce'
  | 'assets'
  | 'references'
  | 'review'
  | 'export'
  | 'publish'
  | 'measure'
  | 'engage';

export type WorkbenchViewMode = 'grid' | 'timeline' | 'kanban';

export interface PostStatusCount {
  draft: number;
  review: number;
  ready: number;
  scheduled: number;
  published: number;
  measured: number;
  archived: number;
}
