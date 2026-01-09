'use client';

import { useState, useEffect, useCallback } from 'react';
import { ControlKnob } from '@/components/knob';

export interface ControlProfile {
  id: string;
  name: string;
  description?: string;
  knobs: ControlKnob[];
  knob_values: Record<string, number>;
  preset_id: string | null;
  workspace_id?: string;
}

export function useControlProfile(workspaceId: string, apiUrl: string) {
  const [profile, setProfile] = useState<ControlProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recentlyChanged, setRecentlyChanged] = useState<string[]>([]);

  // Load control profile
  const loadProfile = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/control-profile`);
      if (!response.ok) {
        throw new Error(`Failed to load control profile: ${response.status}`);
      }
      const data = await response.json();
      setProfile(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load control profile');
      console.error('Failed to load control profile:', err);
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, apiUrl]);

  // Save control profile
  const saveProfile = useCallback(async (updatedProfile: ControlProfile) => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/control-profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedProfile),
      });
      if (!response.ok) {
        throw new Error(`Failed to save control profile: ${response.status}`);
      }
      const data = await response.json();
      setProfile(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save control profile');
      throw err;
    }
  }, [workspaceId, apiUrl]);

  // Update knob value
  const updateKnobValue = useCallback(async (knobId: string, value: number) => {
    if (!profile) return;

    const updatedProfile = {
      ...profile,
      knob_values: {
        ...profile.knob_values,
        [knobId]: value,
      },
    };

    // Track recently changed
    setRecentlyChanged((prev) => {
      if (!prev.includes(knobId)) {
        return [...prev, knobId];
      }
      return prev;
    });

    // Clear recently changed after 3 seconds
    setTimeout(() => {
      setRecentlyChanged((prev) => prev.filter((id) => id !== knobId));
    }, 3000);

    try {
      await saveProfile(updatedProfile);
    } catch (err) {
      console.error('Failed to update knob value:', err);
    }
  }, [profile, saveProfile]);

  // Change preset
  const changePreset = useCallback(async (presetId: string) => {
    try {
      // Load preset
      const presetsResponse = await fetch(`${apiUrl}/api/v1/workspaces/control-profile/presets`);
      if (!presetsResponse.ok) {
        throw new Error('Failed to load presets');
      }
      const presetsData = await presetsResponse.json();
      const preset = presetsData.presets.find((p: any) => p.id === presetId);
      if (!preset) {
        throw new Error(`Preset ${presetId} not found`);
      }

      if (!profile) return;

      const updatedProfile = {
        ...profile,
        preset_id: presetId,
        knob_values: preset.knob_values,
      };

      await saveProfile(updatedProfile);
    } catch (err) {
      console.error('Failed to change preset:', err);
    }
  }, [profile, saveProfile, apiUrl]);

  // Reset to preset
  const resetToPreset = useCallback(async () => {
    if (!profile || !profile.preset_id) return;
    await changePreset(profile.preset_id);
  }, [profile, changePreset]);

  // Unlock knob
  const unlockKnob = useCallback(async (knobId: string) => {
    if (!profile) return;

    const knob = profile.knobs.find((k) => k.id === knobId);
    if (!knob || !knob.is_locked_to_master) return;

    // Create updated knob without lock
    const updatedKnobs = profile.knobs.map((k) =>
      k.id === knobId ? { ...k, is_locked_to_master: false } : k
    );

    const updatedProfile = {
      ...profile,
      knobs: updatedKnobs,
    };

    await saveProfile(updatedProfile);
  }, [profile, saveProfile]);

  useEffect(() => {
    if (workspaceId) {
      loadProfile();
    }
  }, [workspaceId, loadProfile]);

  // Get preset default values
  const getPresetValues = useCallback(async (presetId: string | null): Promise<Record<string, number>> => {
    if (!presetId) return {};

    try {
      const presetsResponse = await fetch(`${apiUrl}/api/v1/workspaces/control-profile/presets`);
      if (!presetsResponse.ok) {
        return {};
      }
      const presetsData = await presetsResponse.json();
      const preset = presetsData.presets.find((p: any) => p.id === presetId);
      return preset?.knob_values || {};
    } catch (err) {
      console.error('Failed to load preset values:', err);
      return {};
    }
  }, [apiUrl]);

  return {
    profile,
    isLoading,
    error,
    recentlyChanged,
    updateKnobValue,
    changePreset,
    resetToPreset,
    unlockKnob,
    getPresetValues,
    reload: loadProfile,
  };
}

