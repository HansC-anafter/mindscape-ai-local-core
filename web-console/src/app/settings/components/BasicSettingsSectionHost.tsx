'use client';

import dynamic from 'next/dynamic';
import { Card } from './Card';

interface BasicSettingsSectionHostProps {
  activeSection?: string;
}

function BasicSectionFallback() {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4 text-sm text-secondary dark:text-gray-400">
      Loading...
    </div>
  );
}

const GoogleOAuthSettings = dynamic(
  () => import('./GoogleOAuthSettings').then((mod) => mod.GoogleOAuthSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const ModelsAndQuotaPanel = dynamic(
  () => import('./panels/ModelsAndQuotaPanel').then((mod) => mod.ModelsAndQuotaPanel),
  { ssr: false, loading: BasicSectionFallback }
);
const LanguagePreferencesSettings = dynamic(
  () => import('./panels/LanguagePreferencesSettings').then((mod) => mod.LanguagePreferencesSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const ModelRouteRegistryPanel = dynamic(
  () => import('./panels/ModelRouteRegistryPanel').then((mod) => mod.ModelRouteRegistryPanel),
  { ssr: false, loading: BasicSectionFallback }
);
const ThemePresetSettings = dynamic(
  () => import('./panels/ThemePresetSettings').then((mod) => mod.ThemePresetSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const CloudExtensionSettings = dynamic(
  () => import('./panels/CloudExtensionSettings').then((mod) => mod.CloudExtensionSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const UnsplashFingerprintsSettings = dynamic(
  () => import('./panels/UnsplashFingerprintsSettings').then((mod) => mod.UnsplashFingerprintsSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const PortConfigurationSettings = dynamic(
  () => import('./panels/PortConfigurationSettings').then((mod) => mod.PortConfigurationSettings),
  { ssr: false, loading: BasicSectionFallback }
);
const RuntimeBackupSettings = dynamic(
  () => import('./panels/RuntimeBackupSettings').then((mod) => mod.RuntimeBackupSettings),
  { ssr: false, loading: BasicSectionFallback }
);

export function BasicSettingsSectionHost({ activeSection }: BasicSettingsSectionHostProps) {
  switch (activeSection) {
    case 'oauth':
      return (
        <div className="space-y-6">
          <GoogleOAuthSettings />
        </div>
      );
    case 'language-preference':
      return (
        <div className="space-y-6">
          <LanguagePreferencesSettings />
        </div>
      );
    case 'theme-preset':
      return (
        <div className="space-y-6">
          <ThemePresetSettings />
        </div>
      );
    case 'cloud-extension':
      return (
        <div className="space-y-6">
          <CloudExtensionSettings />
        </div>
      );
    case 'model-routing-registry':
      return <ModelRouteRegistryPanel />;
    case 'unsplash-fingerprints':
      return (
        <div className="space-y-6">
          <UnsplashFingerprintsSettings />
        </div>
      );
    case 'port-configuration':
      return (
        <div className="space-y-6">
          <PortConfigurationSettings />
        </div>
      );
    case 'runtime-backup':
      return <RuntimeBackupSettings />;
    case 'models-and-quota':
    case 'api-quota':
    case 'embedding':
    case 'llm-chat':
      return (
        <Card className="h-full min-h-0 flex flex-col">
          <ModelsAndQuotaPanel />
        </Card>
      );
    default:
      return null;
  }
}
