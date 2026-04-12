export interface IGFollowingAnalyzerProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  apiUrl?: string;
  onComplete?: (result: AnalysisResult) => void;
  defaultUserDataDir?: string;
  defaultUsername?: string;
}

export interface AccountData {
  username: string;
  display_name: string;
  bio: string;
  is_verified: boolean;
  avatar_url: string;
  account_link: string;
  follower_count_text?: string;
  following_count_text?: string;
  post_count_text?: string;
  profile_bio?: string;
  page_analyzed_at?: string;
  page_analysis_error?: string;
}

export interface AnalysisResult {
  summary: {
    total_accounts: number;
    verified_accounts: number;
    accounts_with_bio: number;
    accounts_with_page_stats: number;
    verified_percentage: number;
    bio_percentage: number;
  };
  accounts: AccountData[];
  metadata: {
    target_username: string;
    workspace_id: string;
    analyzed_at: string;
    total_accounts: number;
    visit_account_pages: boolean;
  };
}

export interface AnalyzerProgress {
  current: number;
  total: number;
  status: string;
  currentAccount?: string;
  stage?: string;
  updatedAt?: string;
  pageIndex?: number;
  pageTotal?: number;
  secondsPerPage?: number;
  etaSeconds?: number;
}

