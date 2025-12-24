"use client";

import React from "react";
import { useParams } from "next/navigation";
import VisualLensManagement from "@/pages/visual-lens/VisualLensManagement";

export default function VisualLensPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  // Extract projectId from query params if needed
  const projectId = undefined; // TODO: Extract from query params when needed

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <VisualLensManagement workspaceId={workspaceId} projectId={projectId} />
    </div>
  );
}


