import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { CaptureSourceReferenceLessonState } from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult } from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import type { MotionPracticeLessonHandoff } from '@/components/workspace/device-binding/practice/motionPracticeLessonHandoff';

export type MotionCoachCapabilityCode = 'yogacoach' | 'dance_motion_coach';

export interface MotionCoachWorkbenchStateInput {
  capabilityCode: MotionCoachCapabilityCode;
  selectedSession: DeviceSessionEntry | null;
  referenceLessonState: CaptureSourceReferenceLessonState | null;
  pendingLessonHandoff?: MotionPracticeLessonHandoff | null;
  launchInput: MotionPracticeLaunchInput | null;
  practiceResult: MotionPracticeLaunchResult | null;
  motionWindowEvents: MotionWindowAppendEvent[];
  closureResult: MotionPracticeClosureResult | null;
}

export type TimelineSegment = {
  id: string;
  title: string;
  startMs: number;
  endMs: number;
};
