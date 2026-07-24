import { MonitorUp, Smartphone, Wrench } from 'lucide-react';

import type { ComponentType, SVGProps } from 'react';

export const MAX_ACTIVE_SOURCE_SLOTS = 3;

export type ProviderId = 'phone' | 'desktop' | 'external';

export type ProviderRailItem = {
  id: ProviderId;
  label: string;
  status: string;
  summary: string;
  readiness: 'ready' | 'bridge_required';
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
};

export const PROVIDER_RAIL_ITEMS: ProviderRailItem[] = [
  {
    id: 'phone',
    label: 'Phone camera',
    status: 'Available',
    summary: 'Use this phone or scan a secure link.',
    readiness: 'ready',
    Icon: Smartphone,
  },
  {
    id: 'desktop',
    label: 'Computer / OBS camera',
    status: 'Available',
    summary: 'USB, virtual camera, or OBS source.',
    readiness: 'ready',
    Icon: MonitorUp,
  },
  {
    id: 'external',
    label: 'External device provider',
    status: 'Bridge required',
    summary: 'Provider bridge, relay, or capture card.',
    readiness: 'bridge_required',
    Icon: Wrench,
  },
];
