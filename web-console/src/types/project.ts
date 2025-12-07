/**
 * Project type definitions for workspace-based projects
 *
 * A Project represents a specific work item within a Workspace - a concrete deliverable
 * such as a web page, book, course, or campaign.
 */

export interface Project {
  id: string;
  type: string;
  title: string;
  home_workspace_id: string;
  flow_id: string;
  state: 'open' | 'closed' | 'archived';
  initiator_user_id: string;
  human_owner_user_id?: string;
  ai_pm_id?: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, any>;
}

export interface ProjectSuggestion {
  mode: 'quick_task' | 'micro_flow' | 'project';
  project_type?: string;
  project_title?: string;
  flow_id?: string;
  initial_spec_md?: string;
  confidence?: number;
}

