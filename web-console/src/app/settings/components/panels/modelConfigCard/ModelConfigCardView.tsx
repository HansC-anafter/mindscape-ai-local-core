'use client';

import { ModelActionsSection } from './ModelActionsSection';
import { ModelDetailsSection } from './ModelDetailsSection';
import { ModelHeader } from './ModelHeader';
import { ModelOverrideSection } from './ModelOverrideSection';
import { ProviderConfigurationSection } from './ProviderConfigurationSection';
import { QuotaUsageSection } from './QuotaUsageSection';
import type { ModelConfigCardViewProps } from './types';

export function ModelConfigCardView(props: ModelConfigCardViewProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-5">
      <div className="space-y-3">
        <ProviderConfigurationSection {...props} />
        <ModelHeader {...props} />
        <ModelOverrideSection {...props} />
        <ModelDetailsSection model={props.model} />
        <ModelActionsSection {...props} />
        <QuotaUsageSection quotaInfo={props.quotaInfo} />
      </div>
    </div>
  );
}
