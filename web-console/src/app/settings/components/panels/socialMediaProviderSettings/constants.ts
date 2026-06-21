import { getApiBaseUrl } from '../../../../../lib/api-url';
import {
  FacebookIcon,
  InstagramIcon,
  LinkedInIcon,
  LineIcon,
  TwitterIcon,
  YouTubeIcon,
} from '../../SocialMediaIcons';
import type { SocialMediaPlatform } from './types';

export const API_URL = getApiBaseUrl();
export const PROFILE_ID = 'default-user';

export const getOAuthCallbackUrl = (provider: string) => `${API_URL}/api/v1/tools/oauth/${provider}/callback`;

export const SOCIAL_MEDIA_PLATFORMS: Record<string, SocialMediaPlatform> = {
  twitter: { label: 'twitterIntegration', Icon: TwitterIcon, color: 'text-blue-500' },
  facebook: { label: 'facebookIntegration', Icon: FacebookIcon, color: 'text-blue-600' },
  instagram: { label: 'instagramIntegration', Icon: InstagramIcon, color: 'text-pink-500' },
  linkedin: { label: 'linkedinIntegration', Icon: LinkedInIcon, color: 'text-blue-700' },
  youtube: { label: 'youtubeIntegration', Icon: YouTubeIcon, color: 'text-red-600' },
  line: { label: 'lineIntegration', Icon: LineIcon, color: 'text-green-500' },
};
