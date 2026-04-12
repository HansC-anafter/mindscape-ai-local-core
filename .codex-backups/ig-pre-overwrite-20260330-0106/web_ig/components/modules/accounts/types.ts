export interface ConnectedAccount {
  channel_config_id: number;
  channel_name: string;
  channel_type: 'instagram';
  status: 'connected' | 'expired' | 'insufficient_permissions';
  expires_at?: string;
  permissions: string[];
  reauth_url?: string;
  page_id?: string;
  username?: string;
}

export interface DiscoveredAccount {
  account_id: string;
  handle: string;
  name?: string;
  bio?: string;
  profile_picture_url?: string;
  follower_count?: number;
  following_count?: number;
  post_count?: number;
  external_url?: string;
  is_verified?: boolean;
  public_email?: string;
  public_phone_number?: string;
  business_address_json?: string;
  grid_posts_json?: string;
  vision_analysis_json?: string;
  fetched_at: string;
  source: 'manual' | 'following_list' | 'search' | 'browser_session';
  sources?: Array<{
    source_account_handle?: string;
    source_profile_ref?: string;
    target_seed?: string;
    schema_version?: string;
    seed_version?: string;
    artifact_id?: string;
    captured_at?: string;
    capture_method?: string;
  }>;
  category?: string;
  tags?: string[];
}

export interface BrowserSessionStatus {
  hasProfile: boolean;
  loggedIn: boolean;
  hasSessionId: boolean;
  sessionExpired: boolean;
  sessionIdCookie?: {
    name?: string;
    domain?: string;
    expires?: number;
  } | null;
  profilePath: string;
  pathSource?: string;
  sessionSource?: string;
  storageStatePath?: string;
  lastChecked: string | null;
  isChecking: boolean;
  message: string;
  igCookieCount: number;
  igCookies: Array<{ name: string; domain: string }>;
}

export interface BrowserProfileInfo {
  name: string;
  path: string;
  logged_in: boolean;
  session_expired: boolean;
  ig_username: string | null;
  ig_user_id: string | null;
  ig_cookie_count: number;
}

export interface BrowserProfileController {
  browserSession: BrowserSessionStatus;
  profileName: string;
  profilePathInput: string;
  availableProfiles: BrowserProfileInfo[];
  selectedProfileInfo: BrowserProfileInfo | null;
  setWorkspaceProfileName: (value: string) => void;
  setProfilePathInput: (value: string) => void;
  setWorkspaceProfilePathOverride: (value: string) => void;
  checkBrowserSessionStatus: (profilePathOverride?: string) => Promise<void>;
  loadProfiles: () => Promise<void>;
}
