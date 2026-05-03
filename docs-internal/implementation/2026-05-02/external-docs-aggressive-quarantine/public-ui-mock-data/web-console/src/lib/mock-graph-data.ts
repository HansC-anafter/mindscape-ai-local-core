/**
 * Mock graph data for Mind-Lens Graph feature
 * Phase 1: Static data for MindProfileCard component
 * Phase 2: Graph data for Sigma.js visualization
 */

export interface MindProfileValue {
  id: string;
  label: string;
  icon: string;
  stance?: 'positive' | 'negative';
}

export interface MindProfileWorldview {
  id: string;
  label: string;
  icon: string;
}

export interface MindProfileAesthetic {
  id: string;
  label: string;
  icon: string;
}

export interface MindProfileDirection {
  values: MindProfileValue[];
  worldviews: MindProfileWorldview[];
  aesthetics: MindProfileAesthetic[];
  knowledge_count: number;
}

export interface MindProfileAction {
  current_strategy: string;
  current_role: string;
  current_rhythm: string;
}

export interface MindProfile {
  direction: MindProfileDirection;
  action: MindProfileAction;
}

export const mockMindProfile: MindProfile = {
  direction: {
    values: [
      { id: 'v1', label: '不剝削合作對象', icon: '🤝', stance: 'positive' },
      { id: 'v2', label: '不做黑箱', icon: '🔍', stance: 'positive' },
      { id: 'v3', label: '對學習者誠實', icon: '💬', stance: 'positive' },
    ],
    worldviews: [
      { id: 'w1', label: 'AI 是人的延伸', icon: '🧠' },
      { id: 'w2', label: '品牌治理解資訊不對稱', icon: '⚖️' },
    ],
    aesthetics: [
      { id: 'a1', label: '克制', icon: '🎨' },
      { id: 'a2', label: '低噪點', icon: '🔇' },
      { id: 'a3', label: '偏冷色', icon: '❄️' },
      { id: 'a4', label: '慢節奏', icon: '🐢' },
    ],
    knowledge_count: 42,
  },
  action: {
    current_strategy: '先寫再設計',
    current_role: '內容策劃',
    current_rhythm: '輕量節奏',
  },
};

// Phase 2: Graph data for Sigma.js
export interface GraphNode {
  id: string;
  label: string;
  category: 'direction' | 'action';
  type: 'value' | 'worldview' | 'aesthetic' | 'knowledge' | 'strategy' | 'role' | 'rhythm';
  icon?: string;
  size?: number;
  description?: string;
  linkedPlaybooks?: string[];
  linkedIntents?: string[];
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: 'supports' | 'conflicts' | 'depends_on' | 'related_to';
  label?: string;
}

export const TYPE_COLORS: Record<string, string> = {
  value: '#10b981',
  worldview: '#6366f1',
  aesthetic: '#f59e0b',
  knowledge: '#8b5cf6',
  strategy: '#ef4444',
  role: '#06b6d4',
  rhythm: '#ec4899',
};

export const mockGraphData = {
  nodes: [
    { id: 'v1', label: '不剝削合作對象', category: 'direction', type: 'value', icon: '🤝', size: 15, description: '與合作夥伴的關係要互惠，不能單方面獲利' },
    { id: 'v2', label: '不做黑箱', category: 'direction', type: 'value', icon: '🔍', size: 15, description: '系統運作要透明，讓使用者理解發生什麼事' },
    { id: 'v3', label: '對學習者誠實', category: 'direction', type: 'value', icon: '💬', size: 15, description: '不誇大效果，不隱瞞限制' },
    { id: 'w1', label: 'AI 是人的延伸', category: 'direction', type: 'worldview', icon: '🧠', size: 18, description: 'AI 是放大人類意圖的工具，不是替代品' },
    { id: 'w2', label: '品牌治理＝解資訊不對稱', category: 'direction', type: 'worldview', icon: '⚖️', size: 18, description: '品牌的核心價值在於降低交易成本' },
    { id: 'w3', label: '生產力悖論', category: 'direction', type: 'worldview', icon: '📈', size: 14 },
    { id: 'a1', label: '克制', category: 'direction', type: 'aesthetic', icon: '🎨', size: 12 },
    { id: 'a2', label: '低噪點', category: 'direction', type: 'aesthetic', icon: '🔇', size: 12 },
    { id: 'a3', label: '偏冷色', category: 'direction', type: 'aesthetic', icon: '❄️', size: 12 },
    { id: 'a4', label: '慢節奏', category: 'direction', type: 'aesthetic', icon: '🐢', size: 12 },
    { id: 'k1', label: 'J 型曲線', category: 'direction', type: 'knowledge', icon: '📚', size: 10 },
    { id: 'k2', label: '景觀 vs 工具理性', category: 'direction', type: 'knowledge', icon: '📖', size: 10 },
    { id: 'k3', label: 'Cynefin 框架', category: 'direction', type: 'knowledge', icon: '🗂️', size: 10 },
    { id: 's1', label: '先寫再設計', category: 'action', type: 'strategy', icon: '📝', size: 15, description: '先用文字釐清思路，再做視覺呈現' },
    { id: 's2', label: '先廣搜再收斂', category: 'action', type: 'strategy', icon: '🔎', size: 15 },
    { id: 's3', label: '保守風險偏好', category: 'action', type: 'strategy', icon: '🛡️', size: 12 },
    { id: 'r1', label: '內容策劃', category: 'action', type: 'role', icon: '👤', size: 16, description: '規劃內容架構、編輯品質' },
    { id: 'r2', label: '正念老師', category: 'action', type: 'role', icon: '🧘', size: 14 },
    { id: 'r3', label: '品牌主理人', category: 'action', type: 'role', icon: '🎯', size: 14 },
    { id: 'r4', label: '工程 Owner', category: 'action', type: 'role', icon: '⚙️', size: 14 },
    { id: 't1', label: '早上 deep work', category: 'action', type: 'rhythm', icon: '🌅', size: 12, description: '上午精神最好，適合處理重要任務' },
    { id: 't2', label: '短迭代', category: 'action', type: 'rhythm', icon: '🔄', size: 12 },
    { id: 't3', label: '20 分鐘快拆版', category: 'action', type: 'rhythm', icon: '⚡', size: 10 },
  ],
  edges: [
    { source: 'v1', target: 'w2', relation: 'supports' },
    { source: 'v2', target: 'w1', relation: 'supports' },
    { source: 'w1', target: 's1', relation: 'related_to' },
    { source: 'w2', target: 's2', relation: 'related_to' },
    { source: 'a1', target: 'r1', relation: 'related_to' },
    { source: 'a4', target: 'r2', relation: 'related_to' },
    { source: 'k1', target: 'w3', relation: 'supports' },
    { source: 'k2', target: 'w1', relation: 'supports' },
    { source: 'r1', target: 's1', relation: 'depends_on' },
    { source: 'r4', target: 's3', relation: 'related_to' },
    { source: 't1', target: 's1', relation: 'supports' },
    { source: 't3', target: 's2', relation: 'conflicts' },
    { source: 'v3', target: 'r2', relation: 'supports' },
    { source: 'w1', target: 'r1', relation: 'related_to' },
  ],
};

