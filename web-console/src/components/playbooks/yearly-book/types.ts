/**
 * Types for yearly-book playbook components
 */

export interface Chapter {
  id: string;
  title: string;
  month: string;
  status: 'draft' | 'in_progress' | 'completed';
  word_count: number;
  content?: string;
  created_at?: string;
  updated_at?: string;
}

export interface BookStructure {
  id: string;
  title: string;
  year: string;
  chapters: Chapter[];
  metadata: {
    total_chapters: number;
    completed_chapters: number;
    progress_percentage: number;
    total_word_count: number;
  };
}

export interface RelatedChapter {
  id: string;
  title: string;
  similarity: number;
  reason?: string;
}

export interface Theme {
  id: string;
  label: string;
  chapters: string[];
  description?: string;
}

export interface KeyPoint {
  id: string;
  text: string;
  chapter_id: string;
  created_at: string;
}

