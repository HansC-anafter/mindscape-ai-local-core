/**
 * Playbooks i18n messages
 * Playbooks, PlaybookChat, and playbook-related errors
 */
import type { MessageKey } from '../keys';

export const playbooksZhTW = {
  // PlaybookChat
  sendMessageFailed: '發送消息失敗，請重試',
  conversationCompleted: '對話已完成',
  enterYourAnswer: '輸入你的回答...',
  sending: '發送中...',
  send: '發送',
  quickStart: '快速開始',
  uploadFile: '上傳檔案',
  dropFilesHere: '拖放檔案到這裡',
  typeMessageOrDropFiles: '輸入訊息或拖放檔案...',

  aiWillUpdateProjectStatus: 'AI 會持續從你的使用記錄中更新這些專案狀態',
  lastUpdated: '上次更新：',
  tellUsOneThingYouWantToPush: '說出一件你最想推進的事',
  aiWillBreakItDown: 'AI 會幫你拆成可執行的步驟',
  autoCreateFirstIntent: '自動建立第一張「長線任務卡」',
  aiWillUseThesePreferences: 'AI 會用這些偏好來規劃任務',
  whatThreeThingsThisWeek: '這週打算做哪 3 件事',
  whatToolsDoYouUse: '平常用什麼工具工作（WP / Notion / ...）',
  whatWorkRhythmDoYouLike: '你喜歡什麼樣的工作節奏',

  // Playbooks
  playbooks: 'Playbooks',
  playbooksTitle: 'Playbook 工作劇本庫',
  playbookWorkflow: '可反覆執行的工作流程',
  playbookStepMindscape: '讀取心智空間',
  playbookStepTools: '使用工具',
  playbookStepMembers: 'AI 成員執行',
  playbooksDescription: '這些成員「一起跟你磨出來的做事方法」，可反覆使用',
  playbookDetailDescription: '這是一段你跟 AI 一起寫的「慣用手法」，它會：先讀哪個心智空間、再用哪些工具、由哪幾個成員分工完成',
  filterTags: '篩選標籤',
  tags: '標籤',
  reload: '重新載入',
  searchPlaybooks: '搜尋 Playbook...',
  systemPlaybook: '系統 Playbook',
  hasTest: '有測試',
  viewDetails: '查看詳情',
  executeNow: '立即執行',
  creating: '建立中...',
  hasPersonalVariant: '已有個人版本',
  coldStartTask: '冷啟動任務',
  noPlaybooksFound: '找不到符合條件的 Playbook',
  noPlaybooks: '還沒有 Playbook。你可以透過 API 建立，或等待後續版本支援 UI 建立。',
  hasPersonalNotes: '有個人備註',
  noDescription: '暫無描述',
  backToList: '返回 Playbook 列表',
  personalNotes: '個人備註',
  myNotes: '💬 我的筆記',
  writeYourNotesHere: '在這裡寫下你的個人筆記...',
  saveNotes: '儲存筆記',
  sopDocument: 'SOP 文件',
  noSopContent: '暫無 SOP 內容',
  associatedIntents: '關聯的意圖卡',
  associatedIntentsIcon: '🎯 關聯的意圖卡',
  usingMindscape: '使用心智空間',
  participatingMembers: '參與 AI 成員',
  usingTools: '會用到的工具',
  requiredTools: '🔧 需要工具',
  usageCount: '使用次數',
  playbookInput: '輸入',
  playbookOutput: '輸出',
  executePlaybook: '開始執行 Playbook',
  executing: '執行中...',
  executionCompleted: '✅ 已完成',
  executionFailed: '執行失敗',
  willReturnAfterCompletion: '完成後會自動返回心智空間並更新進度',

  // Playbook errors
  playbookEnterVariantName: '請輸入版本名稱',
  playbookSelectAtLeastOneSuggestion: '請至少選擇一個建議',
  playbookCreateVariantFailed: '創建變體失敗：{error}',
  playbookVariantCreated: '已建立個人版本「{name}」，後續執行將使用此版本',
  playbookSaveFailed: '儲存失敗',
  playbookCreateVariantFailedError: '建立個人版本失敗：{error}',
  playbookGetSuggestionsFailed: '獲取優化建議失敗：{error}',
  playbookVariantCreatedSuccess: '變體已創建！',

  // Playbook tabs
  playbookTabInfo: '資訊',
  playbookTabSuggestions: '使用建議',
  playbookTabHistory: '執行記錄',
  playbookIntentStatusActive: '進行中',
  playbookIntentStatusCompleted: '已完成',
  playbookIntentPriorityHigh: '高優先級',
  playbookIntentPriorityMedium: '中優先級',
  playbookIntentPriorityLow: '低優先級',
  playbookExecStatusRunning: '運行中',
  playbookStatusLabel: '狀態: ',
  playbookMyVariant: '我的版本：{name}',
  playbookMyVariantDefault: '我的版本',
  findPlaybook: '找 Playbook',
} as const satisfies Partial<Record<MessageKey, string>>;

// Playbook Metadata (Phase 1: i18n localization)
// Separate export for nested metadata structure
// Usage: getPlaybookMetadata(playbookCode, 'name', locale)
export const playbookMetadataZhTW = {
    daily_planning: {
      name: '每日整理 & 優先級',
      description: '幫助用戶整理每日/每週任務，排優先順序，給出可執行清單',
      tags: ['規劃', '每日', '優先級', '工作'],
    },
    content_drafting: {
      name: '內容／文案起稿',
      description: '幫助用戶起草文案、文章、貼文或募資頁內容，包括結構、重點段落和語氣風格',
      tags: ['寫作', '內容', '文案', '行銷'],
    },
    project_breakdown: {
      name: '專案拆解 & 里程碑',
      description: '幫助用戶將專案拆解成階段和里程碑，標註風險與下一步行動',
      tags: ['規劃', '專案', '里程碑', '策略'],
    },
    campaign_asset_playbook: {
      name: '行銷素材生成器',
      description: '從行銷簡報自動生成設計素材，整合 Canva 設計工具',
      tags: ['設計', '行銷', 'canva', '自動化'],
    },
    weekly_review_onboarding: {
      name: '本週工作節奏（冷啟動版）',
      description: '冷啟動專用：快速了解用戶的工作習慣與節奏',
      tags: ['冷啟動', '規劃', '工作節奏', '入門'],
    },
    milestone_planning: {
      name: '里程碑規劃與專案時程',
      description: '規劃關鍵專案里程碑，收集專案目標、識別關鍵節點、定義里程碑標準、設定時程，並識別風險與依賴',
      tags: ['規劃', '專案', '里程碑', '時程'],
    },
    data_analysis: {
      name: '數據分析與趨勢識別',
      description: '分析數據並識別趨勢，透過收集數據和指標、識別數據模式、分析趨勢和異常、計算關鍵指標，並生成分析報告',
      tags: ['數據', '分析', '趨勢', '指標'],
    },
    information_organization: {
      name: '資訊組織與知識庫',
      description: '組織和分類研究資訊，透過收集零散資訊、識別主題和類別、建立知識架構、分類和標籤，並生成結構化知識庫',
      tags: ['研究', '組織', '知識', '資訊'],
    },
    content_analysis: {
      name: '內容分析',
      description: '分析內容品質和 SEO 表現，透過分析內容結構、檢查關鍵字密度、評估可讀性、識別改進機會，並生成分析報告',
      tags: ['seo', '分析', '內容', '品質'],
    },
    publishing_workflow: {
      name: '發布工作流',
      description: '管理內容發布工作流，透過檢查內容完整性、驗證格式和指南、生成發布檢查清單、準備發布備註，並規劃發布時程',
      tags: ['發布', '工作流', '內容', '管理'],
    },
    content_editing: {
      name: '內容編輯與優化',
      description: '編輯和優化內容品質，透過分析內容結構和邏輯、檢查語氣和風格一致性、改善可讀性、檢查品牌指南，並生成編輯建議',
      tags: ['編輯', '內容', '優化', '品質'],
    },
    product_breakdown: {
      name: '產品拆解與需求分析',
      description: '將模糊的產品想法拆解成具體功能點，識別核心價值主張，並生成結構化產品規格',
      tags: ['產品', '設計', '規劃', '需求'],
    },
    market_analysis: {
      name: '市場分析與競爭情報',
      description: '分析市場機會和競爭格局，透過收集市場數據、分析競爭對手、識別市場趨勢、評估機會和風險，並生成市場分析報告',
      tags: ['市場', '分析', '競爭', '情報'],
    },
    ai_guided_recording: {
      name: 'AI 引導課程錄製',
      description: '引導用戶完成課程錄製流程，透過準備課程大綱和腳本、設定錄製參數和提示、引導錄製過程、檢查錄製品質，並生成錄製報告',
      tags: ['錄製', '課程', '製作', '音訊'],
    },
    project_breakdown_onboarding: {
      name: '第一個長線任務（冷啟動版）',
      description: '冷啟動專用：幫助新用戶快速拆解第一個想推進的專案',
      tags: ['冷啟動', '規劃', '專案', '入門'],
    },
    user_story_mapping: {
      name: '用戶故事地圖',
      description: '將產品功能映射到用戶故事，透過收集用戶角色和場景、生成用戶故事（作為...我想要...以便...）、映射功能到故事、優先排序，並生成故事地圖',
      tags: ['產品', '設計', '規劃', '用戶故事'],
    },
    learning_plan: {
      name: '學習計畫創建',
      description: '創建結構化學習計畫，透過拆解學習目標、設計學習路徑、規劃練習方法，並設定里程碑',
      tags: ['學習', '教育', '規劃', '教練'],
    },
    code_review: {
      name: '程式碼審查與品質分析',
      description: '審查程式碼品質和最佳實踐，透過分析程式碼結構、檢查程式碼品質、識別潛在問題、檢查最佳實踐，並生成審查報告',
      tags: ['程式碼', '審查', '品質', '開發'],
    },
    insight_synthesis: {
      name: '洞察綜合與商業情報',
      description: '從數據中提取商業洞察，透過綜合多個數據來源、識別關鍵洞察、連結商業影響、生成行動建議，並創建洞察報告',
      tags: ['洞察', '綜合', '商業', '情報'],
    },
    seo_optimization: {
      name: 'SEO 優化',
      description: '優化內容的 SEO 表現，透過收集目標關鍵字、分析競爭對手、優化標題和描述、改善內容結構，並生成 SEO 報告',
      tags: ['seo', '優化', '內容', '行銷'],
    },
    strategy_planning: {
      name: '策略規劃與執行',
      description: '制定商業策略和執行計畫，透過收集商業目標和現狀、分析市場和競爭、識別機會和威脅、定義策略方向，並規劃執行步驟',
      tags: ['策略', '規劃', '商業', '執行'],
    },
    research_synthesis: {
      name: '研究綜合',
      description: '綜合多個研究來源的資訊，透過收集研究材料和文獻、提取核心觀點、識別共同主題、綜合發現和結論，並生成研究報告',
      tags: ['研究', '綜合', '分析', '知識'],
    },
    technical_documentation: {
      name: '技術文檔生成',
      description: '為程式碼生成技術文檔，透過分析程式碼結構和功能、提取 API 和函數描述、生成文檔結構、編寫使用範例，並生成完整文檔',
      tags: ['文檔', '程式碼', '技術', '開發'],
    },
    note_organization: {
      name: '筆記組織與知識結構化',
      description: '組織和結構化學習筆記，透過收集零散筆記、提取核心概念、建立知識架構，並生成帶有概念關係的結構化筆記',
      tags: ['學習', '筆記', '組織', '知識'],
    },
    copywriting: {
      name: '文案與行銷文案',
      description: '撰寫行銷文案、標題和 CTA。生成多個版本並針對目標受眾優化語氣和表達',
      tags: ['寫作', '文案', '行銷', '內容'],
    },
} as const;

export const playbookMetadataEn = {
    daily_planning: {
      name: 'Daily Planning & Prioritization',
      description: 'Help users organize daily/weekly tasks, prioritize them, and provide an actionable checklist',
      tags: ['planning', 'daily', 'priority', 'work'],
    },
    content_drafting: {
      name: 'Content / Copy Drafting',
      description: 'Help users draft copy, articles, posts, or fundraising page content, including structure, key paragraphs, and tone style',
      tags: ['writing', 'content', 'copywriting', 'marketing'],
    },
    project_breakdown: {
      name: 'Project Breakdown & Milestones',
      description: 'Help users break down projects into phases and milestones, identify risks, and provide next-step action recommendations',
      tags: ['planning', 'project', 'milestone', 'strategy'],
    },
    campaign_asset_playbook: {
      name: 'Campaign Asset Generator',
      description: 'Generate design assets from campaign brief using Canva integration',
      tags: ['design', 'campaign', 'canva', 'automation'],
    },
    weekly_review_onboarding: {
      name: 'Weekly Work Rhythm (Cold Start)',
      description: 'Cold start: Quickly understand user work habits and rhythm',
      tags: ['onboarding', 'planning', 'work-rhythm', 'cold-start'],
    },
    milestone_planning: {
      name: 'Milestone Planning & Project Timeline',
      description: 'Plan key project milestones by collecting project goals, identifying critical nodes, defining milestone criteria, setting timelines, and identifying risks and dependencies',
      tags: ['planning', 'project', 'milestone', 'timeline'],
    },
    data_analysis: {
      name: 'Data Analysis & Trend Identification',
      description: 'Analyze data and identify trends by collecting data and metrics, identifying data patterns, analyzing trends and anomalies, calculating key metrics, and generating analysis reports',
      tags: ['data', 'analysis', 'trends', 'metrics'],
    },
    information_organization: {
      name: 'Information Organization & Knowledge Base',
      description: 'Organize and categorize research information by collecting scattered information, identifying topics and categories, building knowledge architecture, categorizing and tagging, and generating structured knowledge base',
      tags: ['research', 'organization', 'knowledge', 'information'],
    },
    content_analysis: {
      name: 'Content Analysis',
      description: 'Analyze content quality and SEO performance by analyzing content structure, checking keyword density, evaluating readability, identifying improvement opportunities, and generating analysis reports',
      tags: ['seo', 'analysis', 'content', 'quality'],
    },
    publishing_workflow: {
      name: 'Publishing Workflow',
      description: 'Manage content publishing workflow by checking content completeness, validating format and guidelines, generating publishing checklist, preparing publishing notes, and planning publishing schedule',
      tags: ['publishing', 'workflow', 'content', 'management'],
    },
    content_editing: {
      name: 'Content Editing & Optimization',
      description: 'Edit and optimize content quality by analyzing content structure and logic, checking tone and style consistency, improving readability, checking brand guidelines, and generating editing suggestions',
      tags: ['editing', 'content', 'optimization', 'quality'],
    },
    product_breakdown: {
      name: 'Product Breakdown & Requirements Analysis',
      description: 'Break down vague product ideas into concrete feature points, identify core value propositions, and generate structured product specifications',
      tags: ['product', 'design', 'planning', 'requirements'],
    },
    market_analysis: {
      name: 'Market Analysis & Competitive Intelligence',
      description: 'Analyze market opportunities and competitive landscape by collecting market data, analyzing competitors, identifying market trends, evaluating opportunities and risks, and generating market analysis reports',
      tags: ['market', 'analysis', 'competition', 'intelligence'],
    },
    ai_guided_recording: {
      name: 'AI-Guided Course Recording',
      description: 'Guide users through course recording process by preparing course outline and script, setting recording parameters and prompts, guiding recording process, checking recording quality, and generating recording reports',
      tags: ['recording', 'course', 'production', 'audio'],
    },
    project_breakdown_onboarding: {
      name: 'First Long-term Task (Cold Start)',
      description: 'Cold start: Help new users quickly break down their first project to push forward',
      tags: ['onboarding', 'planning', 'project', 'cold-start'],
    },
    user_story_mapping: {
      name: 'User Story Mapping',
      description: 'Map product features to user stories by collecting user roles and scenarios, generating user stories (As a... I want... So that...), mapping features to stories, prioritizing, and generating a story map',
      tags: ['product', 'design', 'planning', 'user_story'],
    },
    learning_plan: {
      name: 'Learning Plan Creation',
      description: 'Create structured learning plans by breaking down learning goals, designing learning paths, planning practice methods, and setting milestones',
      tags: ['learning', 'education', 'planning', 'coaching'],
    },
    code_review: {
      name: 'Code Review & Quality Analysis',
      description: 'Review code quality and best practices by analyzing code structure, checking code quality, identifying potential issues, checking best practices, and generating review reports',
      tags: ['code', 'review', 'quality', 'development'],
    },
    insight_synthesis: {
      name: 'Insight Synthesis & Business Intelligence',
      description: 'Extract business insights from data by synthesizing multiple data sources, identifying key insights, linking business impact, generating action recommendations, and creating insight reports',
      tags: ['insights', 'synthesis', 'business', 'intelligence'],
    },
    seo_optimization: {
      name: 'SEO Optimization',
      description: 'Optimize content for SEO performance by collecting target keywords, analyzing competitors, optimizing titles and descriptions, improving content structure, and generating SEO reports',
      tags: ['seo', 'optimization', 'content', 'marketing'],
    },
    strategy_planning: {
      name: 'Strategy Planning & Execution',
      description: 'Develop business strategy and execution plan by collecting business goals and current state, analyzing market and competition, identifying opportunities and threats, defining strategy direction, and planning execution steps',
      tags: ['strategy', 'planning', 'business', 'execution'],
    },
    research_synthesis: {
      name: 'Research Synthesis',
      description: 'Synthesize information from multiple research sources by collecting research materials and literature, extracting core viewpoints, identifying common themes, synthesizing findings and conclusions, and generating research reports',
      tags: ['research', 'synthesis', 'analysis', 'knowledge'],
    },
    technical_documentation: {
      name: 'Technical Documentation Generation',
      description: 'Generate technical documentation for code by analyzing code structure and functionality, extracting API and function descriptions, generating documentation structure, writing usage examples, and generating complete documentation',
      tags: ['documentation', 'code', 'technical', 'development'],
    },
    note_organization: {
      name: 'Note Organization & Knowledge Structuring',
      description: 'Organize and structure learning notes by collecting scattered notes, extracting core concepts, building knowledge architecture, and generating structured notes with concept relationships',
      tags: ['learning', 'notes', 'organization', 'knowledge'],
    },
    copywriting: {
      name: 'Copywriting & Marketing Copy',
      description: 'Write marketing copy, headlines, and CTAs. Generate multiple versions and optimize tone and expression for target audiences',
      tags: ['writing', 'copywriting', 'marketing', 'content'],
    },
} as const;

export const playbooksEn = {
  // PlaybookChat
  sendMessageFailed: 'Failed to send message, please retry',
  conversationCompleted: 'Conversation completed',
  enterYourAnswer: 'Enter your answer...',
  sending: 'Sending...',
  send: 'Send',
  quickStart: 'Quick Start',
  uploadFile: 'Upload File',
  dropFilesHere: 'Drop files here',
  typeMessageOrDropFiles: 'Type message or drop files...',

  aiWillUpdateProjectStatus: 'AI will continuously update these project statuses from your usage records',
  lastUpdated: 'Last Updated:',
  tellUsOneThingYouWantToPush: 'Tell us one thing you want to push forward',
  aiWillBreakItDown: 'AI will break it down into executable steps',
  autoCreateFirstIntent: 'Automatically create first "Long-term Task Card"',
  aiWillUseThesePreferences: 'AI will use these preferences to plan tasks',
  whatThreeThingsThisWeek: 'What 3 things do you plan to do this week',
  whatToolsDoYouUse: 'What tools do you usually work with (WP / Notion / ...)',
  whatWorkRhythmDoYouLike: 'What work rhythm do you prefer',

  // Playbooks
  playbooks: 'Playbooks',
  playbooksTitle: 'Playbook Library',
  playbookWorkflow: 'Reusable workflows',
  playbookStepMindscape: 'Read Mindscape',
  playbookStepTools: 'Use Tools',
  playbookStepMembers: 'AI Execute',
  playbooksDescription: 'These members\' "shared SOPs" that you\'ve refined together, reusable',
  playbookDetailDescription: 'This is a "habitual workflow" you and AI wrote together. It will: read which Mindscape, use which tools, executed by which members',
  filterTags: 'Filter Tags',
  tags: 'Tags',
  reload: 'Reload',
  searchPlaybooks: 'Search Playbooks...',
  systemPlaybook: 'System Playbook',
  hasTest: 'Tested',
  viewDetails: 'View Details',
  executeNow: 'Execute Now',
  creating: 'Creating...',
  hasPersonalVariant: 'Has Personal Variant',
  coldStartTask: 'Cold Start Task',
  noPlaybooksFound: 'No matching Playbooks found',
  noPlaybooks: 'No Playbooks yet. You can create via API, or wait for future versions to support UI creation.',
  hasPersonalNotes: 'Has personal notes',
  noDescription: 'No description',
  backToList: 'Back to Playbook List',
  personalNotes: 'Personal Notes',
  myNotes: '💬 My Notes',
  writeYourNotesHere: 'Write your personal notes here...',
  saveNotes: 'Save Notes',
  sopDocument: 'SOP Document',
  noSopContent: 'No SOP content',
  associatedIntents: 'Associated Intent Cards',
  associatedIntentsIcon: '🎯 Associated Intent Cards',
  usingMindscape: 'Using Mindscape',
  participatingMembers: 'Participating AI Members',
  usingTools: 'Tools Used',
  requiredTools: '🔧 Required Tools',
  usageCount: 'Usage Count',
  playbookInput: 'Input',
  playbookOutput: 'Output',
  executePlaybook: 'Execute Playbook',
  executing: 'Executing...',
  executionCompleted: '✅ Completed',
  executionFailed: 'Execution Failed',
  willReturnAfterCompletion: 'Will automatically return to Mindscape and update progress after completion',

  // Playbook errors
  playbookEnterVariantName: 'Please enter variant name',
  playbookSelectAtLeastOneSuggestion: 'Please select at least one suggestion',
  playbookCreateVariantFailed: 'Failed to create variant: {error}',
  playbookVariantCreated: 'Personal variant "{name}" created. Future executions will use this variant.',
  playbookSaveFailed: 'Save failed',
  playbookCreateVariantFailedError: 'Failed to create personal variant: {error}',
  playbookGetSuggestionsFailed: 'Failed to get optimization suggestions: {error}',
  playbookVariantCreatedSuccess: 'Variant created!',

  // Playbook tabs
  playbookTabInfo: 'Info',
  playbookTabSuggestions: 'Usage Suggestions',
  playbookTabHistory: 'Execution History',
  playbookIntentStatusActive: 'Active',
  playbookIntentStatusCompleted: 'Completed',
  playbookIntentPriorityHigh: 'High Priority',
  playbookIntentPriorityMedium: 'Medium Priority',
  playbookIntentPriorityLow: 'Low Priority',
  playbookExecStatusRunning: 'Running',
  playbookStatusLabel: 'Status: ',
  playbookMyVariant: 'My Variant: {name}',
  playbookMyVariantDefault: 'My Variant',
  findPlaybook: 'Find Playbook',
} as const satisfies Partial<Record<MessageKey, string>>;

// Helper function to get playbook metadata
export function getPlaybookMetadata(
  playbookCode: string,
  field: 'name' | 'description' | 'tags',
  locale: 'zh-TW' | 'en' = 'zh-TW'
): string | string[] | undefined {
  const metadata = locale === 'zh-TW' ? playbookMetadataZhTW : playbookMetadataEn;
  const playbook = metadata[playbookCode as keyof typeof metadata];
  if (!playbook) return undefined;
  const value = playbook[field];
  if (field === 'tags' && Array.isArray(value)) {
    return value;
  }
  return typeof value === 'string' ? value : (value ? String(value) : undefined);
}
