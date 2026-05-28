'use client';

import React from 'react';

import {
  assertCapabilityWorkbenchInfoMetadata,
  type CapabilityWorkbenchInfoMetadata,
} from '@/types/capability-workbench';

type WorkbenchInfoEntry = {
  id: string;
  sequence: number;
  metadata: CapabilityWorkbenchInfoMetadata;
};

interface CapabilityWorkbenchInfoControlContextValue {
  registerMetadata: (id: string, metadata: CapabilityWorkbenchInfoMetadata) => void;
  unregisterMetadata: (id: string) => void;
}

const CapabilityWorkbenchInfoMetadataContext = React.createContext<CapabilityWorkbenchInfoMetadata | null>(null);
const CapabilityWorkbenchInfoControlContext = React.createContext<CapabilityWorkbenchInfoControlContextValue | null>(null);

let registrationCounter = 0;

function getActiveEntry(entries: WorkbenchInfoEntry[]): WorkbenchInfoEntry | null {
  return entries.reduce<WorkbenchInfoEntry | null>((active, entry) => {
    if (!active || entry.sequence > active.sequence) {
      return entry;
    }
    return active;
  }, null);
}

export function CapabilityWorkbenchInfoProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const sequenceRef = React.useRef(0);
  const [entries, setEntries] = React.useState<WorkbenchInfoEntry[]>([]);
  const activeEntry = React.useMemo(() => getActiveEntry(entries), [entries]);

  const registerMetadata = React.useCallback((
    id: string,
    metadata: CapabilityWorkbenchInfoMetadata,
  ) => {
    const validMetadata = assertCapabilityWorkbenchInfoMetadata(metadata);
    setEntries((current) => {
      const existing = current.find((entry) => entry.id === id);
      if (existing) {
        return current.map((entry) => (
          entry.id === id ? { ...entry, metadata: validMetadata } : entry
        ));
      }
      sequenceRef.current += 1;
      return [
        ...current,
        {
          id,
          sequence: sequenceRef.current,
          metadata: validMetadata,
        },
      ];
    });
  }, []);

  const unregisterMetadata = React.useCallback((id: string) => {
    setEntries((current) => current.filter((entry) => entry.id !== id));
  }, []);

  const value = React.useMemo<CapabilityWorkbenchInfoControlContextValue>(() => ({
    registerMetadata,
    unregisterMetadata,
  }), [registerMetadata, unregisterMetadata]);

  return (
    <CapabilityWorkbenchInfoControlContext.Provider value={value}>
      <CapabilityWorkbenchInfoMetadataContext.Provider value={activeEntry?.metadata || null}>
        {children}
      </CapabilityWorkbenchInfoMetadataContext.Provider>
    </CapabilityWorkbenchInfoControlContext.Provider>
  );
}

export function useCapabilityWorkbenchInfoMetadata(): CapabilityWorkbenchInfoMetadata | null {
  return React.useContext(CapabilityWorkbenchInfoMetadataContext);
}

export function useCapabilityWorkbenchInfoMetadataRegistration(
  metadata: CapabilityWorkbenchInfoMetadata | null,
): void {
  const context = React.useContext(CapabilityWorkbenchInfoControlContext);
  const registrationIdRef = React.useRef<string | null>(null);

  if (registrationIdRef.current === null) {
    registrationCounter += 1;
    registrationIdRef.current = `capability-workbench-info-${registrationCounter}`;
  }

  React.useEffect(() => {
    if (!context || !registrationIdRef.current) {
      return undefined;
    }

    if (!metadata) {
      context.unregisterMetadata(registrationIdRef.current);
      return undefined;
    }

    context.registerMetadata(registrationIdRef.current, metadata);
    return () => {
      if (registrationIdRef.current) {
        context.unregisterMetadata(registrationIdRef.current);
      }
    };
  }, [context, metadata]);
}
