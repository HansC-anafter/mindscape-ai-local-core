'use client';

import React from 'react';
// Import from capability pack components (installed to web-console/src/app/capabilities/{capability_code}/components/)
import { CourseWorkbench } from '../../../../capabilities/yogacoach/components/CourseWorkbench';

/**
 * Course Workbench Page - Workspace Context Route
 *
 * Route: /workspaces/[workspaceId]/yogacoach/course-workbench
 *
 * This route provides the workbench within a workspace context,
 * suitable for navigation from workspace sidebar.
 *
 * Architecture: This page is defined in cloud and will be installed
 * to local-core via capability pack installation mechanism.
 */
export default function CourseWorkbenchPage({
  params
}: {
  params: { workspaceId: string };
}) {
  return (
    <CourseWorkbench workspaceId={params?.workspaceId} />
  );
}
