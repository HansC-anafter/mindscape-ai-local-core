import WorkspaceFastShell from './WorkspaceFastShell';

interface WorkspaceShellPageProps {
  params: {
    workspaceId: string;
  };
}

export default function WorkspaceShellPage({ params }: WorkspaceShellPageProps) {
  return <WorkspaceFastShell workspaceId={params.workspaceId} />;
}
