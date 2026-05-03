export interface WorkScene {
  id: string;
  label: string;
  icon: string;
  description: string;
  defaultAgentType: 'planner' | 'writer' | 'coach' | 'coder';
  defaultPromptTemplate: string;
  suggestedPlaybooks?: string[];
}

export const WORK_SCENES: WorkScene[] = [
  {
    id: 'daily_planning',
    label: 'Daily Planning & Priorities',
    icon: 'DP',
    description: 'Organize today or this week, prioritize the work, and produce an actionable list.',
    defaultAgentType: 'planner',
    defaultPromptTemplate: 'Organize today or this week, prioritize the work, and produce an actionable list. Consider my working rhythm and importance levels.',
    suggestedPlaybooks: ['daily_planning', 'priority_matrix'],
  },
  {
    id: 'project_breakdown',
    label: 'Project Breakdown & Milestones',
    icon: 'PB',
    description: 'Break a project into phases and milestones, then identify risks and next steps.',
    defaultAgentType: 'planner',
    defaultPromptTemplate: 'Break this project into phases and milestones, identify risks for each phase, and recommend next actions.',
    suggestedPlaybooks: ['project_breakdown', 'milestone_planning'],
  },
  {
    id: 'content_drafting',
    label: 'Content & Copy Drafting',
    icon: 'CD',
    description: 'Draft an article, post, fundraising page section, or other content structure.',
    defaultAgentType: 'writer',
    defaultPromptTemplate: 'Draft content with structure, key sections, and a recommended tone of voice.',
    suggestedPlaybooks: ['content_drafting', 'copywriting'],
  },
  {
    id: 'learning_plan',
    label: 'Learning Plan & Notes',
    icon: 'LP',
    description: 'Summarize material or a book, then turn it into a structured learning plan.',
    defaultAgentType: 'planner',
    defaultPromptTemplate: 'Summarize this material or book and create a structured learning plan with a path and practice methods.',
    suggestedPlaybooks: ['learning_plan', 'note_organization'],
  },
  {
    id: 'mindful_dialogue',
    label: 'Mindful Dialogue',
    icon: 'MD',
    description: 'Clarify anxiety or blockers through guided questions and reflection.',
    defaultAgentType: 'coach',
    defaultPromptTemplate: 'Help me clarify the anxiety or blocker I am facing. Use questions to map the current state and suggest reflection directions.',
    suggestedPlaybooks: ['mindful_dialogue', 'coaching_session'],
  },
  {
    id: 'client_collaboration',
    label: 'Client & Partnership Review',
    icon: 'CP',
    description: 'Review a client or partnership situation and list three feasible options with tradeoffs.',
    defaultAgentType: 'planner',
    defaultPromptTemplate: 'Review this client or partnership situation, analyze key issues, and list three feasible options with pros and cons.',
    suggestedPlaybooks: ['client_analysis', 'decision_framework'],
  },
];

export function getWorkSceneById(id: string): WorkScene | undefined {
  return WORK_SCENES.find(scene => scene.id === id);
}

export function getScenesByAgentType(agentType: string): WorkScene[] {
  return WORK_SCENES.filter(scene => scene.defaultAgentType === agentType);
}
