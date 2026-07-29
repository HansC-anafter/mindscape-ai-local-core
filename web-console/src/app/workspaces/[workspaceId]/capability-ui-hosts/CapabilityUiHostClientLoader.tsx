'use client';

import dynamic from 'next/dynamic';
import React from 'react';

import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';
import { getApiBaseUrl } from '@/lib/api-url';
import { loadCapabilityUiLocalization } from '@/lib/capability-ui-localization';
import {
  CAPABILITY_UI_METADATA_TIMEOUT_MS,
  getCapabilityUiMetadata,
  isCapabilityUiLoadAbort,
  isCapabilityUiMetadataFresh,
  readCapabilityUiMetadataCache,
  type CapabilityUiMetadata,
} from '@/lib/capability-ui-metadata-loader';
import { useLocaleContext, useT, type Translator } from '@/lib/i18n';

interface CapabilityUiHostClientLoaderProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
  remoteSurfaceMode?: boolean;
}

function CapabilityUiLoadingState() {
  const t = useT();
  return (
    <div className="flex h-full w-full min-w-0 items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">{t('capabilityUiLoading')}</div>
    </div>
  );
}

const WorkspaceSurfaceShell = dynamic(() => import('./WorkspaceSurfaceShell'), {
  ssr: false,
  loading: CapabilityUiLoadingState,
});
const CapabilityLoadedComponents = dynamic(() => (
  import('../capabilities/[capabilityCode]/CapabilityLoadedComponents')
), {
  ssr: false,
  loading: CapabilityUiLoadingState,
});

function describeCapabilityUiMetadataError(error: unknown, t: Translator): string {
  if (isCapabilityUiLoadAbort(error)) {
    return t('capabilityUiMetadataTimeout', {
      seconds: Math.round(CAPABILITY_UI_METADATA_TIMEOUT_MS / 1000),
    });
  }
  return error instanceof Error ? error.message : t('capabilityUiMetadataFailed');
}

export default function CapabilityUiHostClientLoader({
  workspaceId,
  capabilityCode,
  surfacePath = [],
  remoteSurfaceMode = false,
}: CapabilityUiHostClientLoaderProps) {
  const apiUrl = getApiBaseUrl();
  const { locale } = useLocaleContext();
  const t = useT();
  const [metadata, setMetadata] = React.useState<CapabilityUiMetadata | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    const cached = readCapabilityUiMetadataCache(apiUrl, capabilityCode, workspaceId);
    const cachedMetadata = cached?.metadata || null;
    const forceRefresh = Boolean(cachedMetadata && !isCapabilityUiMetadataFresh(cached));

    setError(null);
    setMetadata(cachedMetadata);
    void getCapabilityUiMetadata(apiUrl, capabilityCode, workspaceId, { forceRefresh })
      .then((nextMetadata) => {
        if (!cancelled) {
          setMetadata(nextMetadata);
        }
      })
      .catch((metadataError) => {
        if (!cancelled && !cachedMetadata) {
          setError(
            metadataError instanceof Error
            && metadataError.message === 'capability_ui_components_unavailable'
              ? t('capabilityUiNoComponents')
              : describeCapabilityUiMetadataError(metadataError, t),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode, t, workspaceId]);

  const localizationPromise = React.useMemo(() => {
    if (!metadata) return null;
    const promise = loadCapabilityUiLocalization({
      apiUrl,
      capabilityCode,
      version: metadata.capabilityInfo.version || 'unversioned',
      requestedLocale: locale,
      descriptor: metadata.capabilityInfo.ui_localization,
    });
    void promise.catch(() => undefined);
    return promise;
  }, [apiUrl, capabilityCode, locale, metadata]);

  let content: React.ReactNode;
  if (error) {
    content = (
      <div className="flex h-full w-full min-w-0 items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('capabilityUiMetadataFailed')}
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
        </div>
      </div>
    );
  } else if (!metadata) {
    content = <CapabilityUiLoadingState />;
  } else {
    content = (
      <CapabilityLoadedComponents
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        capabilityInfo={metadata.capabilityInfo}
        uiComponents={metadata.uiComponents}
        localizationPromise={localizationPromise}
        surfacePath={surfacePath}
        aolRoutePath={buildCapabilityWorkbenchPath(workspaceId, capabilityCode, { surfacePath })}
      />
    );
  }

  return (
    <React.Suspense fallback={<CapabilityUiLoadingState />}>
      <WorkspaceSurfaceShell
        workspaceId={workspaceId}
        activeCapabilityCode={capabilityCode}
        surfacePath={surfacePath}
        remoteSurfaceMode={remoteSurfaceMode}
      >
        {content}
      </WorkspaceSurfaceShell>
    </React.Suspense>
  );
}
