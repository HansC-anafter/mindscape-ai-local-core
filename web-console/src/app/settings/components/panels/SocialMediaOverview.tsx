'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import {
  TwitterIcon,
  FacebookIcon,
  InstagramIcon,
  LinkedInIcon,
  YouTubeIcon,
  LineIcon,
} from '../SocialMediaIcons';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();
const PROFILE_ID = 'default-user';

interface SocialMediaConnection {
  id: string;
  name: string;
  tool_type: string;
  is_active: boolean;
  is_validated: boolean;
  oauth_token?: string;
}

const SOCIAL_MEDIA_PLATFORMS = [
  { id: 'twitter', label: 'twitterIntegration', Icon: TwitterIcon, color: 'text-blue-500' },
  { id: 'facebook', label: 'facebookIntegration', Icon: FacebookIcon, color: 'text-blue-600' },
  { id: 'instagram', label: 'instagramIntegration', Icon: InstagramIcon, color: 'text-pink-500' },
  { id: 'linkedin', label: 'linkedinIntegration', Icon: LinkedInIcon, color: 'text-blue-700' },
  { id: 'youtube', label: 'youtubeIntegration', Icon: YouTubeIcon, color: 'text-red-600' },
  { id: 'line', label: 'lineIntegration', Icon: LineIcon, color: 'text-green-500' },
];

interface SocialMediaOverviewProps {
  onNavigate: (provider: string) => void;
}

export function SocialMediaOverview({ onNavigate }: SocialMediaOverviewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [connections, setConnections] = useState<Record<string, SocialMediaConnection>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    loadConnections();
  }, []);

  // Handle anchor navigation from sub-menu
  useEffect(() => {
    const anchorProvider = searchParams?.get('provider');
    if (anchorProvider && cardRefs.current[anchorProvider]) {
      // Scroll to the card
      setTimeout(() => {
        cardRefs.current[anchorProvider]?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
        // Highlight the card briefly
        const card = cardRefs.current[anchorProvider];
        if (card) {
          card.classList.add('ring-2', 'ring-gray-500', 'ring-offset-2');
          setTimeout(() => {
            card.classList.remove('ring-2', 'ring-gray-500', 'ring-offset-2');
          }, 2000);
        }
      }, 100);
    }
  }, [searchParams]);

  const loadConnections = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}`
      );
      if (!response.ok) {
        throw new Error('Failed to load connections');
      }
      const data: SocialMediaConnection[] = await response.json();
      const connectionsMap: Record<string, SocialMediaConnection> = {};
      data.forEach((conn) => {
        if (SOCIAL_MEDIA_PLATFORMS.some((p) => p.id === conn.tool_type)) {
          connectionsMap[conn.tool_type] = conn;
        }
      });
      setConnections(connectionsMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load connections');
    } finally {
      setLoading(false);
    }
  };

  const handleConfigure = (provider: string) => {
    // Navigate to configuration page
    onNavigate(provider);
    router.push(`/settings?tab=social_media&provider=${provider}&configure=1`);
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8">{t('loading')}</div>
      </Card>
    );
  }

  const connectedCount = Object.values(connections).filter(
    (conn) => conn.is_active && conn.is_validated
  ).length;
  const totalCount = SOCIAL_MEDIA_PLATFORMS.length;

  return (
    <Card>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {t('socialMediaIntegration')}
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {t('socialMediaIntegrationDescription')}
        </p>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-600 dark:text-gray-400">
            {t('connected')}: <span className="font-medium text-gray-900 dark:text-gray-100">{connectedCount}</span> / {totalCount}
          </span>
        </div>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SOCIAL_MEDIA_PLATFORMS.map((platform) => {
          const connection = connections[platform.id];
          const isConnected = connection?.is_active && connection?.is_validated;

          const isHighlighted = searchParams?.get('provider') === platform.id;

          return (
            <div
              key={platform.id}
              ref={(el) => {
                cardRefs.current[platform.id] = el;
              }}
              id={`social-media-${platform.id}`}
              className={`border rounded-lg p-4 transition-all ${
                isHighlighted
                  ? 'border-gray-500 dark:border-gray-500 bg-gray-50 dark:bg-gray-800/20 shadow-md'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600'
              } cursor-pointer`}
              onClick={() => handleConfigure(platform.id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1">
                  <div className={`w-10 h-10 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center ${platform.color} bg-gray-50 dark:bg-gray-800`}>
                    <platform.Icon className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-900 dark:text-gray-100">
                      {t(platform.label as any)}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`inline-flex items-center gap-1 text-xs ${
                          isConnected
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-gray-500 dark:text-gray-400'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isConnected ? 'bg-green-500' : 'bg-gray-400'
                          }`}
                        />
                        {isConnected ? t('socialMediaConnected') : t('socialMediaNotConnected')}
                      </span>
                    </div>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleConfigure(platform.id);
                  }}
                  className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border border-gray-400 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800/20"
                >
                  {t('configure')}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

