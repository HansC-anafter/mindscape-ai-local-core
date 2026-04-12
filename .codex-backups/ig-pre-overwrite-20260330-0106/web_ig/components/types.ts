/**
 * IG Post Type Definitions
 *
 * Shared type definitions for IG UI components
 * This file is included in the capability pack for use in Local-Core
 */

export type PostStatus = 'draft' | 'review' | 'ready' | 'scheduled' | 'published' | 'measured' | 'archived';

export interface IGPost {
  id: string;
  artifact_id: string;
  execution_id?: string;
  text: string;
  hashtags: string[];
  status: PostStatus;
  platform: string;
  created_at: string;
  updated_at: string;
  series_id?: string;
  arc_id?: string;
  scheduled_time?: string;
  narrative_phase?: string;
  emotion?: string;
  images?: string[]; // Array of image URLs
  post_path?: string;
  post_id?: string;
  frontmatter?: Record<string, any>;
  content?: string;
}

export interface WorkbenchContext {
  workspace_id: string;
  activeModule: string | null;
  viewMode: 'grid' | 'timeline' | 'kanban';
  statusFilter: PostStatus | 'all';

  selectedPostId: string | null;
  selectedSeriesId: string | null;
  selectedAccountId: string | null;
  selectionScope: 'single' | 'batch' | 'filtered';
}

