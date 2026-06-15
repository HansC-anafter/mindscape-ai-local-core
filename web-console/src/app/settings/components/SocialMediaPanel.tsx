'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SocialMediaOverview } from './panels/SocialMediaOverview';
import { SocialMediaProviderSettings } from './panels/SocialMediaProviderSettings';

export function SocialMediaPanel({
  activeProvider,
  workspaceId,
}: {
  activeProvider?: string;
  workspaceId?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Check if we should show the configuration page after an explicit configure action.
  // Sub-menu clicks should only show overview with anchor
  const shouldShowConfig = searchParams?.get('configure' as any) === '1' && activeProvider;

  const handleNavigate = (provider: string) => {
    // Navigate to configuration page
    const params = new URLSearchParams({
      tab: 'social_media',
      provider,
      configure: '1',
    });
    if (workspaceId) {
      params.set('workspace_id', workspaceId);
    }
    router.push(`/settings?${params.toString()}`);
  };

  const handleBack = () => {
    const params = new URLSearchParams({ tab: 'social_media' });
    if (workspaceId) {
      params.set('workspace_id', workspaceId);
    }
    router.push(`/settings?${params.toString()}`);
  };

  if (shouldShowConfig && activeProvider) {
    return <SocialMediaProviderSettings provider={activeProvider} workspaceId={workspaceId} onBack={handleBack} />;
  }

  return <SocialMediaOverview onNavigate={handleNavigate} />;
}
