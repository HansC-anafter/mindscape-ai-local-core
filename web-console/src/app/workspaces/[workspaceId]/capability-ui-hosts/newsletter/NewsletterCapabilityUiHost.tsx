'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as CampaignEditorModule0 from '@/app/capabilities/newsletter/components/CampaignEditor';
import * as NewsletterPageModule1 from '@/app/capabilities/newsletter/components/NewsletterPage';
import * as TemplatePreviewModule2 from '@/app/capabilities/newsletter/components/TemplatePreview';

const componentModules: Record<string, Record<string, unknown>> = {
  "CampaignEditor": CampaignEditorModule0 as Record<string, unknown>,
  "NewsletterPage": NewsletterPageModule1 as Record<string, unknown>,
  "TemplatePreview": TemplatePreviewModule2 as Record<string, unknown>,
};

export default function NewsletterCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
