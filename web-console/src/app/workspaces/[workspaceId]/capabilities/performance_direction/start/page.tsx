import { redirect } from 'next/navigation';

import { buildPerformanceDirectionStartPath } from '../routePaths';

type PerformanceDirectionStartPageProps = {
  params: {
    workspaceId: string;
  };
};

export default function PerformanceDirectionStartPage({
  params,
}: PerformanceDirectionStartPageProps) {
  const workspaceId = String(params.workspaceId || '').trim();

  redirect(buildPerformanceDirectionStartPath(workspaceId));
}
