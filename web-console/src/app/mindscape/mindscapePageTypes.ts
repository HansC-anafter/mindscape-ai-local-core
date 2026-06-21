export interface OnboardingState {
  task1_completed: boolean;
  task2_completed: boolean;
  task3_completed: boolean;
  task1_completed_at?: string;
  task2_completed_at?: string;
  task3_completed_at?: string;
  is_onboarding?: boolean;
  has_state?: boolean;
}

export interface OnboardingStatusResponse {
  onboarding_state: OnboardingState;
}

export interface MindscapeSuggestion {
  id: string;
  type: 'project' | 'principle' | 'preference' | 'intent';
  title: string;
  description: string;
  source: string;
  confidence: number;
}

export interface CurrentMode {
  mainMode: string;
  weeklyFocus: string[];
  aiAssistants: string[];
}

export interface MindscapeSelfDescription {
  identity?: string;
  solving?: string;
  thinking?: string;
}

export interface MindscapeProfile {
  self_description?: MindscapeSelfDescription;
  [key: string]: unknown;
}

export interface MindscapeIntent {
  id: string;
  title: string;
  status?: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface MindscapeWorkspaceSummary {
  id: string;
  [key: string]: unknown;
}

export interface SelfIntroPayload {
  identity: string;
  solving: string;
  thinking: string;
}

export interface MindscapeIntentPayload {
  title: string;
  description: string;
  tags: string[];
  status: string;
  priority: string;
}

export type SuggestionReviewAction = 'accept' | 'dismiss';

export interface FirstWorkspaceResult {
  ok: boolean;
  workspaceId: string | null;
}
