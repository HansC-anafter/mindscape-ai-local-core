import { LocalVideoMotionSmokePage } from '@/components/workspace/motion-video-smoke/LocalVideoMotionSmokePage';

interface MotionVideoSmokeRouteProps {
  params: {
    workspaceId: string;
  };
}

export default function MotionVideoSmokeRoute({ params }: MotionVideoSmokeRouteProps) {
  return <LocalVideoMotionSmokePage workspaceId={params.workspaceId} />;
}
