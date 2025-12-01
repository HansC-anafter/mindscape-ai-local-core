'use client';

import { useState, useEffect, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';
import type {
  BackendConfig,
  Profile,
  ProfilePreferences,
  ReviewPreferences,
} from '../types';

const PROFILE_ID = 'default-user';

interface UseBasicSettingsReturn {
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
  config: BackendConfig | null;
  profile: Profile | null;
  mode: string;
  remoteUrl: string;
  remoteToken: string;
  openaiKey: string;
  anthropicKey: string;
  enableHabitSuggestions: boolean;
  reviewPreferences: ReviewPreferences;
  setMode: (mode: string) => void;
  setRemoteUrl: (url: string) => void;
  setRemoteToken: (token: string) => void;
  setOpenaiKey: (key: string) => void;
  setAnthropicKey: (key: string) => void;
  setEnableHabitSuggestions: (enabled: boolean) => void;
  setReviewPreferences: (prefs: Partial<ReviewPreferences>) => void;
  loadConfig: () => Promise<void>;
  loadProfile: () => Promise<void>;
  saveSettings: () => Promise<void>;
  clearError: () => void;
  clearSuccess: () => void;
}

const defaultReviewPreferences: ReviewPreferences = {
  cadence: 'manual',
  day_of_week: 6,
  day_of_month: 28,
  time_of_day: '21:00',
  min_entries: 10,
  min_insight_events: 3,
};

export function useBasicSettings(): UseBasicSettingsReturn {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [mode, setMode] = useState('local');
  const [remoteUrl, setRemoteUrl] = useState('');
  const [remoteToken, setRemoteToken] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [anthropicKey, setAnthropicKey] = useState('');
  const [enableHabitSuggestions, setEnableHabitSuggestions] = useState(false);
  const [reviewPreferences, setReviewPreferencesState] = useState<ReviewPreferences>(
    defaultReviewPreferences
  );

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<BackendConfig>(
        `/api/v1/config/backend?profile_id=${PROFILE_ID}`
      );
      setConfig(data);
      setMode(data.current_mode);
      setRemoteUrl(data.remote_crs_url || '');
      setRemoteToken('');
      setOpenaiKey('');
      setAnthropicKey('');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load configuration';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadProfile = useCallback(async () => {
    try {
      const profileData = await settingsApi.get<Profile>(
        `/api/v1/mindscape/profiles/${PROFILE_ID}`
      );
      setProfile(profileData);
      setEnableHabitSuggestions(
        profileData?.preferences?.enable_habit_suggestions || false
      );

      const reviewPrefs = profileData?.preferences?.review_preferences;
      if (reviewPrefs) {
        setReviewPreferencesState({
          ...defaultReviewPreferences,
          ...reviewPrefs,
        });
      }
    } catch (err) {
      console.error('Failed to load profile:', err);
    }
  }, []);

  const saveSettings = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await settingsApi.put(`/api/v1/config/backend?profile_id=${PROFILE_ID}`, {
        mode,
        remote_crs_url: mode === 'remote_crs' ? remoteUrl : undefined,
        remote_crs_token: mode === 'remote_crs' && remoteToken.trim() !== '' ? remoteToken : undefined,
        openai_api_key: mode === 'local' && openaiKey.trim() !== '' ? openaiKey : undefined,
        anthropic_api_key: mode === 'local' && anthropicKey.trim() !== '' ? anthropicKey : undefined,
      });

      if (profile) {
        const updatedPreferences: ProfilePreferences = {
          ...profile.preferences,
          enable_habit_suggestions: enableHabitSuggestions,
          review_preferences: reviewPreferences,
        };

        await settingsApi.put(`/api/v1/mindscape/profiles/${PROFILE_ID}`, {
          preferences: updatedPreferences,
        });
      }

      setSuccess('Settings saved successfully');
      await loadConfig();
      await loadProfile();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save settings';
      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  }, [
    mode,
    remoteUrl,
    remoteToken,
    openaiKey,
    anthropicKey,
    enableHabitSuggestions,
    reviewPreferences,
    profile,
    loadConfig,
    loadProfile,
  ]);

  const setReviewPreferences = useCallback((prefs: Partial<ReviewPreferences>) => {
    setReviewPreferencesState((current) => ({
      ...current,
      ...prefs,
    }));
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const clearSuccess = useCallback(() => {
    setSuccess(null);
  }, []);

  useEffect(() => {
    loadConfig();
    loadProfile();
  }, [loadConfig, loadProfile]);

  return {
    loading,
    saving,
    error,
    success,
    config,
    profile,
    mode,
    remoteUrl,
    remoteToken,
    openaiKey,
    anthropicKey,
    enableHabitSuggestions,
    reviewPreferences,
    setMode,
    setRemoteUrl,
    setRemoteToken,
    setOpenaiKey,
    setAnthropicKey,
    setEnableHabitSuggestions,
    setReviewPreferences,
    loadConfig,
    loadProfile,
    saveSettings,
    clearError,
    clearSuccess,
  };
}
