'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SocialMediaOverview } from './panels/SocialMediaOverview';
import { SocialMediaProviderSettings } from './panels/SocialMediaProviderSettings';

export function SocialMediaPanel({ activeProvider }: { activeProvider?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Check if we should show configuration page (only when explicitly clicking "配置" button)
  // Sub-menu clicks should only show overview with anchor
  const shouldShowConfig = searchParams?.get('configure') === '1' && activeProvider;

  const handleNavigate = (provider: string) => {
    // Navigate to configuration page
    router.push(`/settings?tab=social_media&provider=${provider}&configure=1`);
  };

  const handleBack = () => {
    router.push('/settings?tab=social_media');
  };

  if (shouldShowConfig && activeProvider) {
    return <SocialMediaProviderSettings provider={activeProvider} onBack={handleBack} />;
  }

  return <SocialMediaOverview onNavigate={handleNavigate} />;
}

