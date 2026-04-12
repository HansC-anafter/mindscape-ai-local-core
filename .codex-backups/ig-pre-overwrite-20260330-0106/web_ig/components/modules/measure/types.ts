export interface Metrics {
  likes?: number;
  comments?: number;
  shares?: number;
  saves?: number;
  reach?: number;
  impressions?: number;
  engagement_rate?: number;
  backfilled_at?: string;
  backfill_source?: 'manual' | 'api' | 'scraper';
}

export interface PerformanceElement {
  element_type: 'hashtag' | 'caption' | 'image' | 'timing' | 'series';
  element_value: string;
  performance_level: 'high' | 'medium' | 'low';
  impact_score?: number;
}

export interface Analysis {
  overall_performance: 'high' | 'medium' | 'low';
  threshold_met: boolean;
  recommendations: string[];
  performance_elements: PerformanceElement[];
}

