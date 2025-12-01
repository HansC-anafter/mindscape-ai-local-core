// Work Scenes Configuration
// Aligns with console-kit's Channel concept, but presented as personal work scenes

export interface WorkScene {
  id: string;
  label: string;
  icon: string;
  description: string;
  defaultAgentType: 'planner' | 'writer' | 'coach' | 'coder';
  defaultPromptTemplate: string;
  suggestedPlaybooks?: string[]; // Future Playbook recommendations
}

export const WORK_SCENES: WorkScene[] = [
  {
    id: 'daily_planning',
    label: '每日整理 & 優先級',
    icon: '🗓',
    description: '幫我整理今天 / 這週要做的事，排優先順序，給一個可執行清單。',
    defaultAgentType: 'planner',
    defaultPromptTemplate: '幫我整理今天/這週要做的事，排優先順序，並給出一個可執行的清單。請考慮我的工作節奏和重要程度。',
    suggestedPlaybooks: ['daily_planning', 'priority_matrix'],
  },
  {
    id: 'project_breakdown',
    label: '專案拆解 & 里程碑',
    icon: '📦',
    description: '幫我把「X 專案」拆成階段和里程碑，並標註風險與下一步。',
    defaultAgentType: 'planner',
    defaultPromptTemplate: '幫我把這個專案拆解成階段和里程碑，標註每個階段的風險點，並給出下一步行動建議。',
    suggestedPlaybooks: ['project_breakdown', 'milestone_planning'],
  },
  {
    id: 'content_drafting',
    label: '內容／文案起稿',
    icon: '✍️',
    description: '幫我生出一版草稿：文章／貼文／募資頁 section。',
    defaultAgentType: 'writer',
    defaultPromptTemplate: '幫我起草一份內容草稿，包括結構、重點段落和建議的語氣風格。',
    suggestedPlaybooks: ['content_drafting', 'copywriting'],
  },
  {
    id: 'learning_plan',
    label: '學習計畫 & 筆記整理',
    icon: '🎓',
    description: '幫我整理這一段內容／這本書重點，並排成一份學習計畫。',
    defaultAgentType: 'planner',
    defaultPromptTemplate: '幫我整理這段內容/這本書的重點，並制定一份結構化的學習計畫，包括學習路徑和練習方式。',
    suggestedPlaybooks: ['learning_plan', 'note_organization'],
  },
  {
    id: 'mindful_dialogue',
    label: '心智 / 情緒整理對話',
    icon: '🧠',
    description: '幫我梳理目前的焦慮 / 卡住的地方，用提問方式陪我看清狀態。',
    defaultAgentType: 'coach',
    defaultPromptTemplate: '幫我梳理目前感到焦慮或卡住的地方，用提問的方式陪我釐清現狀，並給出一些思考方向。',
    suggestedPlaybooks: ['mindful_dialogue', 'coaching_session'],
  },
  {
    id: 'client_collaboration',
    label: '客戶／合作案梳理',
    icon: '🤝',
    description: '幫我整理這個客戶 / 合作案的現況，列出3個可行選項與利弊。',
    defaultAgentType: 'planner',
    defaultPromptTemplate: '幫我整理這個客戶/合作案的現況，分析關鍵問題，並列出3個可行的選項，說明每個選項的利弊。',
    suggestedPlaybooks: ['client_analysis', 'decision_framework'],
  },
];

// Get scene configuration by scene ID
export function getWorkSceneById(id: string): WorkScene | undefined {
  return WORK_SCENES.find(scene => scene.id === id);
}

// Get scenes by agent type
export function getScenesByAgentType(agentType: string): WorkScene[] {
  return WORK_SCENES.filter(scene => scene.defaultAgentType === agentType);
}

