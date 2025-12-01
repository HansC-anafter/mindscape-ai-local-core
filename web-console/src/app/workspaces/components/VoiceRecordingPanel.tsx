'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useT } from '@/lib/i18n';

interface ScriptLine {
  id: string;
  line_number: number;
  text: string;
  status: 'pending' | 'recording' | 'recorded' | 'retrying' | 'skipped';
  audio_path?: string;
  duration?: number;
  recorded_at?: string;
  retry_count: number;
}

interface RecordingSession {
  id: string;
  instructor_id: string;
  workspace_id?: string;
  script_path?: string;
  script_text?: string;
  script_lines: ScriptLine[];
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  voice_mode: string;
  voice_profile_id?: string;
  master_audio_path?: string;
  created_at: string;
  updated_at: string;
  progress: {
    total: number;
    recorded: number;
    pending: number;
    percentage: number;
  };
}

interface VoiceRecordingPanelProps {
  workspaceId: string;
  apiUrl?: string;
  sessionId?: string;
}

export default function VoiceRecordingPanel({
  workspaceId,
  apiUrl = 'http://localhost:8000',
  sessionId: initialSessionId,
}: VoiceRecordingPanelProps) {
  const t = useT();
  const [session, setSession] = useState<RecordingSession | null>(null);
  const [currentLineIndex, setCurrentLineIndex] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingCountdown, setRecordingCountdown] = useState<number | null>(null);
  const [isPlayingDemo, setIsPlayingDemo] = useState(false);
  const [isPlayingPreview, setIsPlayingPreview] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCreatingSession, setIsCreatingSession] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recordingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (initialSessionId) {
      loadSession(initialSessionId);
    }
  }, [initialSessionId]);

  useEffect(() => {
    if (session && session.status === 'in_progress') {
      const interval = setInterval(() => {
        loadSession(session.id);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [session?.id, session?.status]);

  const loadSession = async (sessionId: string) => {
    try {
      setLoading(true);
      const response = await fetch(`${apiUrl}/api/v1/voice-recording/sessions/${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        setSession(data);
        if (data.script_lines && data.script_lines.length > 0) {
          const firstPendingIndex = data.script_lines.findIndex(
            (line: ScriptLine) => line.status === 'pending'
          );
          if (firstPendingIndex >= 0) {
            setCurrentLineIndex(firstPendingIndex);
          }
        }
      } else {
        setError(`Failed to load session: ${response.statusText}`);
      }
    } catch (err) {
      setError(`Failed to load session: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const createSession = async (scriptText: string, scriptLines?: string[]) => {
    try {
      setIsCreatingSession(true);
      setError(null);
      const response = await fetch(`${apiUrl}/api/v1/voice-recording/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          instructor_id: workspaceId,
          workspace_id: workspaceId,
          script_text: scriptText,
          script_lines: scriptLines,
          voice_mode: 'tts',
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSession(data);
        setCurrentLineIndex(0);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create session');
      }
    } catch (err) {
      setError(`Failed to create session: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsCreatingSession(false);
    }
  };

  const playDemo = async (lineId: string) => {
    if (!session) return;

    try {
      setIsPlayingDemo(true);
      const response = await fetch(
        `${apiUrl}/api/v1/voice-recording/sessions/${session.id}/play-demo`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            line_id: lineId,
          }),
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (audioRef.current) {
          audioRef.current.src = `${apiUrl}${data.audio_path}`;
          audioRef.current.play();
          audioRef.current.onended = () => {
            setIsPlayingDemo(false);
          };
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to play demo');
        setIsPlayingDemo(false);
      }
    } catch (err) {
      setError(`Failed to play demo: ${err instanceof Error ? err.message : 'Unknown error'}`);
      setIsPlayingDemo(false);
    }
  };

  const recordLine = async (lineId: string, durationLimit: number = 30.0) => {
    if (!session) return;

    try {
      setIsRecording(true);
      setRecordingCountdown(Math.floor(durationLimit));

      const countdownInterval = setInterval(() => {
        setRecordingCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(countdownInterval);
            return null;
          }
          return prev - 1;
        });
      }, 1000);

      const response = await fetch(
        `${apiUrl}/api/v1/voice-recording/sessions/${session.id}/record-line`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            line_id: lineId,
            duration_limit: durationLimit,
          }),
        }
      );

      clearInterval(countdownInterval);
      setRecordingCountdown(null);

      if (response.ok) {
        const data = await response.json();
        await loadSession(session.id);

        if (data.audio_path && audioRef.current) {
          audioRef.current.src = `${apiUrl}${data.audio_path}`;
          setIsPlayingPreview(true);
          audioRef.current.play();
          audioRef.current.onended = () => {
            setIsPlayingPreview(false);
          };
        }

        moveToNextLine();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to record line');
      }
    } catch (err) {
      setError(`Failed to record line: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsRecording(false);
      setRecordingCountdown(null);
    }
  };

  const retryLine = async (lineId: string) => {
    if (!session) return;

    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/voice-recording/sessions/${session.id}/retry-line`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            line_id: lineId,
          }),
        }
      );

      if (response.ok) {
        await loadSession(session.id);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to retry line');
      }
    } catch (err) {
      setError(`Failed to retry line: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const mergeRecordings = async () => {
    if (!session) return;

    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/voice-recording/sessions/${session.id}/merge`,
        {
          method: 'POST',
        }
      );

      if (response.ok) {
        const data = await response.json();
        await loadSession(session.id);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to merge recordings');
      }
    } catch (err) {
      setError(`Failed to merge recordings: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const downloadMaster = () => {
    if (!session || !session.master_audio_path) return;

    const downloadUrl = `${apiUrl}/api/v1/voice-recording/sessions/${session.id}/master`;
    window.open(downloadUrl, '_blank');
  };

  const moveToNextLine = () => {
    if (!session) return;

    const nextIndex = currentLineIndex + 1;
    if (nextIndex < session.script_lines.length) {
      setCurrentLineIndex(nextIndex);
    }
  };

  const moveToPreviousLine = () => {
    if (currentLineIndex > 0) {
      setCurrentLineIndex(currentLineIndex - 1);
    }
  };

  const currentLine = session?.script_lines[currentLineIndex];

  if (!session && !isCreatingSession) {
    return (
      <div className="p-6 bg-white rounded-lg shadow">
        <h2 className="text-xl font-semibold mb-4">Voice Recording</h2>
        <div className="space-y-4">
          <textarea
            className="w-full p-3 border rounded-md"
            rows={10}
            placeholder="Enter script text here (one line per recording)..."
            id="script-input"
          />
          <button
            onClick={() => {
              const textarea = document.getElementById('script-input') as HTMLTextAreaElement;
              if (textarea && textarea.value.trim()) {
                createSession(textarea.value.trim());
              }
            }}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            disabled={isCreatingSession}
          >
            {isCreatingSession ? 'Creating...' : 'Create Recording Session'}
          </button>
        </div>
      </div>
    );
  }

  if (loading && !session) {
    return (
      <div className="p-6 bg-white rounded-lg shadow">
        <p>Loading session...</p>
      </div>
    );
  }

  if (!session) return null;

  return (
    <div className="p-6 bg-white rounded-lg shadow">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-2">Voice Recording Session</h2>
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-600">
            Progress: {session.progress.recorded} / {session.progress.total} lines (
            {session.progress.percentage}%)
          </div>
          <div className="w-64 bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all"
              style={{ width: `${session.progress.percentage}%` }}
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">{error}</div>
      )}

      {currentLine && (
        <div className="mb-6 p-4 border rounded-lg">
          <div className="mb-4">
            <div className="text-sm text-gray-500 mb-1">
              Line {currentLine.line_number} of {session.script_lines.length}
            </div>
            <div className="text-lg font-medium">{currentLine.text}</div>
          </div>

          <div className="flex gap-2 mb-4">
            <button
              onClick={() => playDemo(currentLine.id)}
              disabled={isPlayingDemo || isRecording}
              className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
            >
              {isPlayingDemo ? 'Playing...' : 'Play Demo'}
            </button>

            <button
              onClick={() => recordLine(currentLine.id)}
              disabled={isRecording || isPlayingDemo}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
            >
              {isRecording
                ? recordingCountdown !== null
                  ? `Recording... ${recordingCountdown}s`
                  : 'Recording...'
                : 'Record'}
            </button>

            {currentLine.status === 'recorded' && (
              <>
                <button
                  onClick={() => {
                    if (currentLine.audio_path && audioRef.current) {
                      audioRef.current.src = `${apiUrl}${currentLine.audio_path}`;
                      setIsPlayingPreview(true);
                      audioRef.current.play();
                      audioRef.current.onended = () => {
                        setIsPlayingPreview(false);
                      };
                    }
                  }}
                  disabled={isPlayingPreview}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  {isPlayingPreview ? 'Playing...' : 'Play Preview'}
                </button>

                <button
                  onClick={() => retryLine(currentLine.id)}
                  disabled={loading}
                  className="px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 disabled:opacity-50"
                >
                  Retry
                </button>
              </>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={moveToPreviousLine}
              disabled={currentLineIndex === 0}
              className="px-3 py-1 text-sm border rounded-md hover:bg-gray-50 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={moveToNextLine}
              disabled={currentLineIndex >= session.script_lines.length - 1}
              className="px-3 py-1 text-sm border rounded-md hover:bg-gray-50 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      <div className="mt-6 flex gap-2">
        <button
          onClick={mergeRecordings}
          disabled={loading || session.progress.recorded === 0}
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? 'Merging...' : 'Merge All Recordings'}
        </button>

        {session.master_audio_path && (
          <button
            onClick={downloadMaster}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
          >
            Download Master Audio
          </button>
        )}
      </div>

      <audio ref={audioRef} />
    </div>
  );
}
