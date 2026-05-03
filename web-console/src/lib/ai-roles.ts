export interface AIRole {
  id: string;
  nameKey: string;
  icon: string;
  descriptionKey: string;
  agentType: 'planner' | 'writer' | 'coach' | 'coder' | 'visual_design_partner';
  suggestedTasksKeys: string[];
  playbooks?: string[];
  categories?: string[];
  aiTeamMembers?: string[];
  aiTeamTitleKey?: string;
  aiTeamDescriptionKey?: string;
}

export const AI_ROLES: AIRole[] = [
  {
    id: 'product_designer',
    nameKey: 'roleProductDesigner',
    icon: 'PD',
    descriptionKey: 'roleProductDesignerDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleProductDesignerTask1',
      'roleProductDesignerTask2',
      'roleProductDesignerTask3',
      'roleProductDesignerTask4',
    ],
    playbooks: ['product_breakdown', 'user_story_mapping'],
    categories: ['design'],
  },
  {
    id: 'writing_partner',
    nameKey: 'roleWritingPartner',
    icon: 'WP',
    descriptionKey: 'roleWritingPartnerDescription',
    agentType: 'writer',
    suggestedTasksKeys: [
      'roleWritingPartnerTask1',
      'roleWritingPartnerTask2',
      'roleWritingPartnerTask3',
      'roleWritingPartnerTask4',
    ],
    playbooks: ['content_drafting', 'copywriting'],
    categories: ['content'],
  },
  {
    id: 'learning_coach',
    nameKey: 'roleLearningCoach',
    icon: 'LC',
    descriptionKey: 'roleLearningCoachDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleLearningCoachTask1',
      'roleLearningCoachTask2',
      'roleLearningCoachTask3',
      'roleLearningCoachTask4',
    ],
    playbooks: ['learning_plan', 'note_organization'],
    categories: ['coaching', 'productivity'],
  },
  {
    id: 'emotional_coach',
    nameKey: 'roleEmotionalCoach',
    icon: 'EC',
    descriptionKey: 'roleEmotionalCoachDescription',
    agentType: 'coach',
    suggestedTasksKeys: [
      'roleEmotionalCoachTask1',
      'roleEmotionalCoachTask2',
      'roleEmotionalCoachTask3',
      'roleEmotionalCoachTask4',
    ],
    playbooks: ['mindful_dialogue', 'coaching_session'],
    categories: ['coaching'],
  },
  {
    id: 'project_manager',
    nameKey: 'roleProjectManager',
    icon: 'PM',
    descriptionKey: 'roleProjectManagerDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleProjectManagerTask1',
      'roleProjectManagerTask2',
      'roleProjectManagerTask3',
      'roleProjectManagerTask4',
    ],
    playbooks: ['project_breakdown', 'milestone_planning'],
    categories: ['business', 'productivity'],
  },
  {
    id: 'daily_organizer',
    nameKey: 'roleDailyOrganizer',
    icon: 'DO',
    descriptionKey: 'roleDailyOrganizerDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleDailyOrganizerTask1',
      'roleDailyOrganizerTask2',
      'roleDailyOrganizerTask3',
      'roleDailyOrganizerTask4',
    ],
    playbooks: ['daily_planning', 'priority_matrix'],
    categories: ['productivity'],
  },
  {
    id: 'seo_consultant',
    nameKey: 'roleSEOConsultant',
    icon: 'SEO',
    descriptionKey: 'roleSEOConsultantDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleSEOConsultantTask1',
      'roleSEOConsultantTask2',
      'roleSEOConsultantTask3',
      'roleSEOConsultantTask4',
    ],
    playbooks: ['seo_optimization', 'content_analysis'],
    categories: ['business', 'content'],
  },
  {
    id: 'content_editor',
    nameKey: 'roleContentEditor',
    icon: 'CE',
    descriptionKey: 'roleContentEditorDescription',
    agentType: 'writer',
    suggestedTasksKeys: [
      'roleContentEditorTask1',
      'roleContentEditorTask2',
      'roleContentEditorTask3',
      'roleContentEditorTask4',
    ],
    playbooks: ['content_editing', 'publishing_workflow'],
    categories: ['content'],
  },
  {
    id: 'research_assistant',
    nameKey: 'roleResearchAssistant',
    icon: 'RA',
    descriptionKey: 'roleResearchAssistantDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleResearchAssistantTask1',
      'roleResearchAssistantTask2',
      'roleResearchAssistantTask3',
      'roleResearchAssistantTask4',
    ],
    playbooks: ['research_synthesis', 'information_organization'],
    categories: ['productivity'],
  },
  {
    id: 'code_reviewer',
    nameKey: 'roleCodeReviewer',
    icon: 'CR',
    descriptionKey: 'roleCodeReviewerDescription',
    agentType: 'coder',
    suggestedTasksKeys: [
      'roleCodeReviewerTask1',
      'roleCodeReviewerTask2',
      'roleCodeReviewerTask3',
      'roleCodeReviewerTask4',
    ],
    playbooks: ['code_review', 'technical_documentation'],
    categories: ['technical'],
  },
  {
    id: 'data_analyst',
    nameKey: 'roleDataAnalyst',
    icon: 'DA',
    descriptionKey: 'roleDataAnalystDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleDataAnalystTask1',
      'roleDataAnalystTask2',
      'roleDataAnalystTask3',
      'roleDataAnalystTask4',
    ],
    playbooks: ['data_analysis', 'insight_synthesis'],
    categories: ['business', 'technical'],
  },
  {
    id: 'business_strategist',
    nameKey: 'roleBusinessStrategist',
    icon: 'BS',
    descriptionKey: 'roleBusinessStrategistDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleBusinessStrategistTask1',
      'roleBusinessStrategistTask2',
      'roleBusinessStrategistTask3',
      'roleBusinessStrategistTask4',
    ],
    playbooks: ['strategy_planning', 'market_analysis'],
    categories: ['business'],
  },
  {
    id: 'course_production_partner',
    nameKey: 'roleCourseProductionPartner',
    icon: 'CP',
    descriptionKey: 'roleCourseProductionPartnerDescription',
    agentType: 'planner',
    suggestedTasksKeys: [
      'roleCourseProductionPartnerTask1',
      'roleCourseProductionPartnerTask2',
      'roleCourseProductionPartnerTask3',
      'roleCourseProductionPartnerTask4',
    ],
    playbooks: ['ai_guided_recording'],
    categories: ['coaching', 'content'],
    aiTeamMembers: [
      'roleCourseProductionPartnerTeamMember1',
      'roleCourseProductionPartnerTeamMember2',
      'roleCourseProductionPartnerTeamMember3',
      'roleCourseProductionPartnerTeamMember4',
      'roleCourseProductionPartnerTeamMember5',
      'roleCourseProductionPartnerTeamMember6',
    ],
    aiTeamTitleKey: 'roleCourseProductionPartnerTeamTitle',
    aiTeamDescriptionKey: 'roleCourseProductionPartnerTeamDescription',
  },
];

export function getRoleById(id: string): AIRole | undefined {
  return AI_ROLES.find(role => role.id === id);
}

export function getRolesByAgentType(agentType: string): AIRole[] {
  return AI_ROLES.filter(role => role.agentType === agentType);
}

export function getLocalizedRole(role: AIRole, t: (key: any) => string): {
  name: string;
  description: string;
  suggestedTasks: string[];
} {
  return {
    name: t(role.nameKey),
    description: t(role.descriptionKey),
    suggestedTasks: role.suggestedTasksKeys.map(key => t(key)),
  };
}
