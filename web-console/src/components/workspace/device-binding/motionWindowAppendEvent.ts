import type { AppendMotionWindowResponse } from '@/lib/motion-analysis/motionWindowClient';
import type { MotionWindowSummary } from '@/lib/motion-analysis/livePoseWindow';

export type MotionWindowAppendEvent = {
  liveSessionId: string;
  response: AppendMotionWindowResponse;
  summary: MotionWindowSummary;
};
