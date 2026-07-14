'use client';

import React from 'react';

import CapabilitySettingsExtensionSlot, {
  type SettingsExtensionOwnerContract,
} from '@/components/capabilities/CapabilitySettingsExtensionSlot';

interface CapabilityExtensionSlotProps {
  section: string;
  workspaceId: string;
  ownerContract?: SettingsExtensionOwnerContract;
}

export default function CapabilityExtensionSlot({
  section,
  workspaceId,
  ownerContract,
}: CapabilityExtensionSlotProps) {
  return (
    <CapabilitySettingsExtensionSlot
      section={section}
      workspaceId={workspaceId}
      workspaceScopedOnly
      ownerContract={ownerContract}
    />
  );
}
